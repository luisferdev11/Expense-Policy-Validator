"""Run one variant of a registered experiment on the frozen dev set (research R4).

    uv run python -I eval/experiments/run_dev.py --experiment E14 --variant gpt-oss-20b
    uv run python -I eval/experiments/run_dev.py --experiment E5 --variant translate
    uv run python -I eval/experiments/run_dev.py --experiment E16 --variant jev-1.13
    uv run python -I eval/experiments/run_dev.py --experiment E16 --variant jev-hybrid
    (E16 jev-1.13 also takes --repeat-subset 20: a second pass on a random subset, cache bypassed)
    add --offline to replay from the cache with no model call

Uses the pipeline's normaliser and OpenRouter adapter with the variant's pin, one per-variant
cache of literal answers, and one `classify-dev-item` trace per item. It refuses an experiment
without Luis's approval, or registered on a different frozen set. Never reads the receipts.

E16 (jev for the category): both variants share one jev cache, so jev is asked once per item. The
hybrid's gpt-oss-120b side is never billed: it reads the committed E14 answers (the rows file, the
cache directory is gitignored) in offline mode, so an item without one is an offline miss.
"""

from __future__ import annotations

import argparse
import json
import random
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

from eval.experiments.devset import frozen_hash, load_frozen
from expense_validator.adapters.classification_cache import ClassificationCache, cache_key
from expense_validator.adapters.hybrid_classifier import HybridClassifier
from expense_validator.adapters.openrouter.classifier import OpenRouterClassifier
from expense_validator.adapters.openrouter.decision_classifier import (
    DecisionClassifier,
)
from expense_validator.adapters.openrouter.decision_classifier import (
    Transport as DecisionTransport,
)
from expense_validator.adapters.openrouter.models import HYBRID, JEV, PINS, REFERENCE
from expense_validator.adapters.openrouter.prompt import PROMPT_VERSION
from expense_validator.adapters.openrouter.translator import Translator
from expense_validator.adapters.tracing import make_tracer
from expense_validator.app.classifiers import sync_prompt_links
from expense_validator.domain.models import CacheEntry, Classification, ClassifierRequest
from expense_validator.domain.normaliser import clean
from expense_validator.paths import REPO_ROOT
from expense_validator.ports.classifier import ItemClassifier
from expense_validator.ports.tracer import Tracer

PLAN = REPO_ROOT / "explorations" / "research" / "experiments_plan.yaml"
RESULTS = REPO_ROOT / "explorations" / "results" / "iter2"
CACHE_DIR = RESULTS / "cache"
ITERATION_CAP_USD = 1.00
E16_VARIANTS = (JEV, HYBRID)
E16_BUDGET_USD = 0.10
E16_SEED = 20261012
E16_DIR = RESULTS / "E16"


class RegistrationError(RuntimeError):
    """The experiment is not registered, not approved, or registered on another dev set."""


def check_registration(experiment: str, plan_path: Path, digest: str) -> dict[str, Any]:
    plan = yaml.safe_load(plan_path.read_text(encoding="utf-8"))
    entries = {e.get("id"): e for e in plan.get("iteration_2", []) if isinstance(e, dict)}
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
                "unclassified_reason": c.unclassified_reason,
                "served_by": c.source.served_by,
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


def load_env() -> None:
    """Load `.env` into the environment, from the repository or, in a git worktree, from the main
    checkout (the worktree has no `.env` of its own). Never prints or returns a value."""
    from dotenv import load_dotenv

    candidates = [REPO_ROOT / ".env"]
    common = subprocess.run(
        ["git", "rev-parse", "--git-common-dir"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()
    if common:
        candidates.append((REPO_ROOT / common).resolve().parent / ".env")
    for path in candidates:
        if path.is_file():
            load_dotenv(path)
            return


# E16 (jev for the category, specs/007-jev-classifier/contracts/e16-rule.md)


def _jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def e14_detail_cache(
    items: list[dict[str, Any]],
    rows_path: Path | None = None,
    cache_path: Path | None = None,
) -> ClassificationCache:
    """The reference's committed E14 answers as a cache, rebuilt from the rows file.

    The cache directory is gitignored, so a clone has only the rows, which keep each literal answer
    (`raw_content`), its request id, cost and serving provider. Each entry is keyed as the E14 run
    keyed it (cleaned description, merchant, MCC, the reference's pin, `cls-v2`). A local cache
    file is read too when it exists. Nothing is saved: the cache lives in memory.
    """
    rows = {
        r["item_id"]: r for r in _jsonl(rows_path or RESULTS / "E14" / f"{REFERENCE.name}.jsonl")
    }
    cache = ClassificationCache(cache_path or CACHE_DIR / f"{REFERENCE.name}.jsonl")
    for item in items:
        row = rows.get(item["item_id"])
        if row is None or row.get("raw_content") is None:
            continue
        request = ClassifierRequest(
            description_clean=clean(item["description"]),
            merchant_name=item["merchant_name"],
            mcc=item["mcc"],
        )
        key = cache_key(request, REFERENCE.model_id, REFERENCE.endpoint, PROMPT_VERSION)
        if cache.get(key) is None:
            cache.put(
                CacheEntry(
                    cache_key=key,
                    content=row["raw_content"],
                    model_id=REFERENCE.model_id,
                    provider_endpoint=REFERENCE.endpoint,
                    prompt_version=PROMPT_VERSION,
                    request_id=row.get("request_id"),
                    cost_usd=row.get("cost_usd"),
                    prompt_tokens=None,
                    completion_tokens=None,
                    reasoning=None,
                    served_by=row.get("served_by"),
                )
            )
    return cache


def e16_spend(cache_dir: Path = CACHE_DIR) -> float:
    """What E16 has billed: every jev answer cached so far, the repeat pass included."""
    total = 0.0
    for path in sorted(cache_dir.glob(f"{JEV}*.jsonl")):
        for entry in _jsonl(path):
            total += entry.get("cost_usd") or 0.0
    return total


def e16_cap(cache_dir: Path = CACHE_DIR) -> float:
    """What may still be billed in this process: what remains of E16's USD 0.10 and of the
    iteration's USD 1.00."""
    remaining_e16 = E16_BUDGET_USD - e16_spend(cache_dir)
    iteration = ITERATION_CAP_USD - sum(
        entry.get("cost_usd") or 0.0
        for path in sorted(cache_dir.glob("*.jsonl"))
        for entry in _jsonl(path)
    )
    return max(0.0, min(remaining_e16, iteration))


def build_e16_classifier(
    variant: str,
    tracer: Tracer,
    items: list[dict[str, Any]],
    *,
    offline: bool,
    cap_usd: float,
    jev_cache: ClassificationCache,
    detail_cache: ClassificationCache | None = None,
    prompt_links: dict[str, Any] | None = None,
    jev_transport: DecisionTransport | None = None,
    raw_dir: Path | None = None,
) -> ItemClassifier:
    """`jev-1.13` or `jev-hybrid`. Both variants share the jev cache. The hybrid's detail side is
    the reference on its committed E14 answers, offline: it can never bill."""
    links = prompt_links or {}
    extra = {} if raw_dir is None else {"raw_dir": raw_dir}
    jev = DecisionClassifier(
        jev_cache,
        tracer,
        transport=jev_transport,
        offline=offline,
        cap_usd=cap_usd,
        prompt_link=links.get("decision"),
        **extra,
    )
    if variant == JEV:
        return jev
    if variant != HYBRID:
        raise ValueError(f"E16 variants are {E16_VARIANTS}, not {variant!r}")
    detail = OpenRouterClassifier(
        detail_cache or e14_detail_cache(items),
        tracer,
        offline=True,
        pin=REFERENCE,
        prompt_link=links.get("chat"),
    )
    return HybridClassifier(jev, detail)


def _answer_of(entry: CacheEntry | None) -> tuple[float | None, float | None, str | None]:
    """The top probability, the reported confidence and the source jev's answer used, read from the
    literal body (None when absent or outside [0, 1])."""
    if entry is None:
        return None, None, None
    try:
        body = json.loads(entry.content or "")
        answer = body["answers"]["category"]
        choice = answer["choice"]
    except (json.JSONDecodeError, KeyError, TypeError):
        return None, None, None

    def unit(value: Any) -> float | None:
        ok = not isinstance(value, bool) and isinstance(value, int | float) and 0 <= value <= 1
        return float(value) if ok else None

    probabilities = answer.get("probabilities")
    top = unit(probabilities.get(choice)) if isinstance(probabilities, dict) else None
    reported = unit(answer.get("confidence"))
    source = (entry.reasoning or "").removeprefix("confidence_source=") or None
    return top, reported, source


def e16_row(
    item: dict[str, Any], variant: str, classifier: ItemClassifier, c: Classification
) -> dict[str, Any]:
    """One row of an E16 variant: E14's fields plus the two confidence sources and the latency."""
    if isinstance(classifier, HybridClassifier):
        jev_key, detail_key = classifier.last_keys or ("", "")
        jev_entry = classifier.category_source.cache.get(jev_key)
        detail_entry = classifier.detail_source.cache.get(detail_key)
        latency = classifier.last_latency_s
        flags = {
            "hybrid_conflict": classifier.last_flags.get("hybrid_conflict", False),
            "detail_violation": classifier.last_flags.get("detail_violation", False),
        }
    else:
        assert isinstance(classifier, DecisionClassifier)
        jev_entry = classifier.cache.get(c.source.cache_key)
        detail_entry = None
        latency = classifier.last_latency_s
        flags = {}
    top, reported, source = _answer_of(jev_entry)
    return {
        "item_id": item["item_id"],
        "variant": variant,
        "model_id": classifier.model_id,
        "prompt_version": classifier.prompt_version,
        "status": c.status,
        "category": c.category,
        "restricted": c.restricted,
        "confidence": c.confidence,
        "top_probability": top,
        "reported_confidence": reported,
        "confidence_source": source,
        "subtype": c.subtype,
        "recipient_kind": c.recipient_kind,
        "recipient_name": c.recipient_name,
        "raw_content": jev_entry.content if jev_entry else None,
        "detail_raw_content": detail_entry.content if detail_entry else None,
        "request_id": c.source.request_id,
        "cost_usd": c.source.cost_usd,
        "latency_s": latency,
        "cache_hit": c.source.cache_hit,
        "unclassified_reason": c.unclassified_reason,
        "served_by": c.source.served_by,
        **flags,
    }


def run_variant_e16(
    variant: str,
    items: list[dict[str, Any]],
    classifier: ItemClassifier,
    tracer: Tracer,
    out_path: Path,
    run_label: str,
) -> list[dict[str, Any]]:
    rows = []
    for item in sorted(items, key=lambda i: i["item_id"]):
        with tracer.receipt_trace(
            item["item_id"],
            run_label,
            input={k: item[k] for k in ("description", "language", "merchant_name", "mcc")},
            name="classify-dev-item",
        ) as root:
            request = ClassifierRequest(
                description_clean=clean(item["description"]),
                merchant_name=item["merchant_name"],
                mcc=item["mcc"],
            )
            c = classifier.classify(item["item_id"], request)
            row = e16_row(item, variant, classifier, c)
            root.update(
                output={"predicted": row["category"], "expected": item.get("category")},
                metadata={"experiment": "E16", "variant": variant},
            )
        rows.append(row)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8"
    )
    return rows


def repeat_subset_ids(items: list[dict[str, Any]], n: int) -> list[str]:
    """The random n-item subset of the repeatability pass (seed 20261012), in item order."""
    ids = sorted(i["item_id"] for i in items)
    return sorted(random.Random(E16_SEED).sample(ids, min(n, len(ids))))


def run_repeat_pass(
    items: list[dict[str, Any]],
    n: int,
    first_rows: list[dict[str, Any]],
    tracer: Tracer,
    out_path: Path,
    *,
    offline: bool,
    cap_usd: float,
    cache_path: Path,
    prompt_link: Any = None,
    jev_transport: DecisionTransport | None = None,
    raw_dir: Path | None = None,
) -> list[dict[str, Any]]:
    """Ask jev again for a random subset, with the first pass's cache bypassed, and record how often
    the category changed. It decides nothing; its calls count in the budget (its answers are
    cached in a file of their own, which `e16_spend` reads)."""
    wanted = set(repeat_subset_ids(items, n))
    first = {r["item_id"]: r for r in first_rows}
    extra = {} if raw_dir is None else {"raw_dir": raw_dir}
    classifier = DecisionClassifier(
        ClassificationCache(cache_path),
        tracer,
        transport=jev_transport,
        offline=offline,
        cap_usd=cap_usd,
        prompt_link=prompt_link,
        **extra,
    )
    rows = []
    for item in sorted(items, key=lambda i: i["item_id"]):
        if item["item_id"] not in wanted:
            continue
        with tracer.receipt_trace(
            item["item_id"],
            "E16-jev-1.13-repeat",
            input={k: item[k] for k in ("description", "language", "merchant_name", "mcc")},
            name="classify-dev-item",
        ):
            request = ClassifierRequest(
                description_clean=clean(item["description"]),
                merchant_name=item["merchant_name"],
                mcc=item["mcc"],
            )
            c = classifier.classify(item["item_id"], request)
        rows.append(
            {
                "item_id": item["item_id"],
                "first_category": first[item["item_id"]]["category"],
                "second_category": c.category,
                "second_status": c.status,
                "unclassified_reason": c.unclassified_reason,
                "changed": c.status == "classified"
                and c.category != first[item["item_id"]]["category"],
                "request_id": c.source.request_id,
                "cost_usd": c.source.cost_usd,
                "cache_hit": c.source.cache_hit,
            }
        )
    classifier.cache.save()  # type: ignore[attr-defined]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8"
    )
    return rows


def _main_e16(args: argparse.Namespace) -> int:
    if args.variant not in E16_VARIANTS:
        raise SystemExit(f"E16's variants are {', '.join(E16_VARIANTS)}")
    if args.repeat_subset and args.variant != JEV:
        raise SystemExit("--repeat-subset applies to the jev-1.13 variant")
    items = load_frozen()
    tracer = make_tracer()
    links = sync_prompt_links(args.variant, tracer, args.offline)
    cap = e16_cap()
    jev_cache = ClassificationCache(CACHE_DIR / f"{JEV}.jsonl")
    classifier = build_e16_classifier(
        args.variant,
        tracer,
        items,
        offline=args.offline,
        cap_usd=cap,
        jev_cache=jev_cache,
        prompt_links=links,
    )
    out = E16_DIR / f"{args.variant}.jsonl"
    rows = run_variant_e16(args.variant, items, classifier, tracer, out, f"E16-{args.variant}")
    jev_cache.save()
    repeated: list[dict[str, Any]] = []
    if args.repeat_subset:
        repeated = run_repeat_pass(
            items,
            args.repeat_subset,
            rows,
            tracer,
            E16_DIR / "repeat.jsonl",
            offline=args.offline,
            cap_usd=e16_cap(),
            cache_path=CACHE_DIR / f"{JEV}.repeat.jsonl",
            prompt_link=links.get("decision"),
        )
    tracer.flush(timeout_s=15.0)
    failed = sum(1 for r in rows if r["status"] != "classified")
    gateway = sum(1 for r in rows if r["unclassified_reason"] == "gateway_error")
    print(
        f"E16/{args.variant}: {len(rows)} items, {getattr(classifier, 'calls_made', 0)} calls, "
        f"{failed} unclassified ({gateway} gateway errors: re-run to retry them), "
        f"billed USD {getattr(classifier, 'run_spend_usd', 0.0):.6f}; "
        f"E16 total USD {e16_spend():.6f} of {E16_BUDGET_USD:.2f}"
        + (f"; repeat pass {len(repeated)} items" if repeated else ""),
        file=sys.stderr,
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment", required=True, choices=["E14", "E5", "E16"])
    parser.add_argument("--variant", required=True)
    parser.add_argument("--offline", action="store_true")
    parser.add_argument(
        "--repeat-subset",
        type=int,
        default=0,
        help="E16 jev-1.13 only: ask again for a random subset of this size, cache bypassed",
    )
    args = parser.parse_args(argv)

    load_env()
    check_registration(args.experiment, PLAN, frozen_hash())
    if args.experiment == "E16":
        return _main_e16(args)
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
    gateway = sum(1 for r in rows if r["unclassified_reason"] == "gateway_error")
    print(
        f"{args.experiment}/{args.variant}: {len(rows)} items, {classifier.calls_made} calls, "
        f"{failed} unclassified ({gateway} gateway errors: re-run to retry them), "
        f"billed USD {classifier.run_spend_usd:.6f}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
