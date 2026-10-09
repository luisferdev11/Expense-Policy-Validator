"""Run one variant of a registered experiment on the frozen dev set (research R4).

    uv run python -I eval/experiments/run_dev.py --experiment E14 --variant gpt-oss-20b
    uv run python -I eval/experiments/run_dev.py --experiment E5 --variant translate
    add --offline to replay from the cache with no model call

Uses the pipeline's normaliser and OpenRouter adapter with the variant's pin, one per-variant
cache of literal answers, and one `classify-dev-item` trace per item. It refuses an experiment
without Luis's approval, or registered on a different frozen set. Never reads the receipts.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml

from eval.experiments.devset import frozen_hash, load_frozen
from expense_validator.adapters.classification_cache import ClassificationCache
from expense_validator.adapters.openrouter.classifier import OpenRouterClassifier
from expense_validator.adapters.openrouter.models import PINS, REFERENCE
from expense_validator.adapters.openrouter.prompt import PROMPT_VERSION
from expense_validator.adapters.openrouter.translator import Translator
from expense_validator.adapters.tracing import make_tracer
from expense_validator.domain.models import ClassifierRequest
from expense_validator.domain.normaliser import clean
from expense_validator.paths import REPO_ROOT
from expense_validator.ports.tracer import Tracer

PLAN = REPO_ROOT / "explorations" / "research" / "experiments_plan.yaml"
RESULTS = REPO_ROOT / "explorations" / "results" / "iter2"
CACHE_DIR = RESULTS / "cache"
ITERATION_CAP_USD = 1.00


class RegistrationError(RuntimeError):
    """The experiment is not registered, not approved, or registered on another dev set."""


def check_registration(experiment: str, plan_path: Path, digest: str) -> dict[str, Any]:
    plan = yaml.safe_load(plan_path.read_text(encoding="utf-8"))
    entries = {e.get("id"): e for e in plan.get("experiments", []) if isinstance(e, dict)}
    entry = entries.get(experiment)
    if entry is None:
        raise RegistrationError(f"{experiment} is not registered in {plan_path.name}")
    if not entry.get("approved_by"):
        raise RegistrationError(f"{experiment} is registered but not approved by Luis")
    if entry.get("data") != digest:
        raise RegistrationError(f"{experiment} was registered on another dev set hash")
    return dict(entry)


def run_variant(
    experiment: str,
    variant: str,
    items: list[dict[str, Any]],
    classifier: OpenRouterClassifier,
    tracer: Tracer,
    out_path: Path,
    run_label: str,
    translator: Translator | None = None,
) -> list[dict[str, Any]]:
    rows = []
    for item in sorted(items, key=lambda i: i["item_id"]):
        with tracer.receipt_trace(
            item["item_id"],
            run_label,
            input={k: item[k] for k in ("description", "language", "merchant_name", "mcc")},
            name="classify-dev-item",
        ) as root:
            translation = None
            text = clean(item["description"])
            if translator is not None:
                translation = translator.translate(text, item["language"])
                text = clean(translation) if translation else text
            request = ClassifierRequest(
                description_clean=text, merchant_name=item["merchant_name"], mcc=item["mcc"]
            )
            c = classifier.classify(item["item_id"], request)
            entry = classifier.cache.get(c.source.cache_key)
            row = {
                "item_id": item["item_id"],
                "variant": variant,
                "model_id": classifier.model_id,
                "prompt_version": PROMPT_VERSION,
                "status": c.status,
                "category": c.category,
                "restricted": c.restricted,
                "confidence": c.confidence,
                "subtype": c.subtype,
                "recipient_kind": c.recipient_kind,
                "recipient_name": c.recipient_name,
                "raw_content": entry.content if entry else None,
                "request_id": c.source.request_id,
                "cost_usd": c.source.cost_usd,
                "cache_hit": c.source.cache_hit,
                "translation": translation,
            }
            root.update(
                output={"predicted": row["category"], "expected": item.get("category")},
                metadata={"experiment": experiment, "variant": variant},
            )
        rows.append(row)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8"
    )
    return rows


def iteration_spend() -> float:
    total = 0.0
    for path in sorted(CACHE_DIR.glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                total += json.loads(line).get("cost_usd") or 0.0
    return total


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment", required=True, choices=["E14", "E5"])
    parser.add_argument("--variant", required=True)
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args(argv)

    from dotenv import load_dotenv

    load_dotenv(REPO_ROOT / ".env")
    check_registration(args.experiment, PLAN, frozen_hash())
    items = load_frozen()
    translator = None
    if args.experiment == "E5":
        if args.variant != "translate":
            raise SystemExit("E5's only new variant is 'translate'; the original comes from E14")
        pin = REFERENCE
        items = [i for i in items if i["language"] != "en"]
    else:
        if args.variant not in PINS:
            raise SystemExit(f"unknown pin {args.variant}; choose from {sorted(PINS)}")
        pin = PINS[args.variant]
    tracer = make_tracer()
    cache = ClassificationCache(CACHE_DIR / f"{pin.name}.jsonl")
    remaining = ITERATION_CAP_USD - iteration_spend() + cache.total_cost_usd()
    classifier = OpenRouterClassifier(
        cache, tracer, offline=args.offline, pin=pin, cap_usd=remaining
    )
    if args.experiment == "E5":
        translator = Translator(CACHE_DIR / "translations.jsonl", tracer, offline=args.offline)
    out = RESULTS / args.experiment / f"{args.variant}.jsonl"
    rows = run_variant(
        args.experiment, args.variant, items, classifier, tracer, out,
        f"{args.experiment}-{args.variant}", translator,
    )  # fmt: skip
    cache.save()
    if translator is not None:
        translator.save()
    tracer.flush(timeout_s=15.0)
    failed = sum(1 for r in rows if r["status"] != "classified")
    print(
        f"{args.experiment}/{args.variant}: {len(rows)} items, {classifier.calls_made} calls, "
        f"{failed} unclassified, billed USD {classifier.run_spend_usd:.6f}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
