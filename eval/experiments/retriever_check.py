"""The retriever comparison (research R9): the trigger map versus every rule.

    uv run python -I eval/experiments/retriever_check.py

Runs the engine twice on each receipt, once with the rules the trigger map retrieves and once
with all of them, and lists every receipt whose findings differ. The cases are the 13 synthetic
engine fixtures and the 32 receipts with their committed classifications, replayed offline.
Outcomes are compared with each other, never with answers, and no model is called.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from typing import Any

from expense_validator.adapters.classification_cache import ClassificationCache
from expense_validator.adapters.config_files import load_settings
from expense_validator.adapters.openrouter.classifier import OpenRouterClassifier
from expense_validator.adapters.receipts_file import load_receipts
from expense_validator.adapters.tracing import NoopTracer
from expense_validator.app.pipeline import classify_receipt
from expense_validator.domain.engine.context import build_context
from expense_validator.domain.engine.evaluate import evaluate
from expense_validator.domain.engine.registry import REGISTRY
from expense_validator.domain.engine.settings import Settings
from expense_validator.domain.models import (
    Classification,
    ClassificationSource,
    ClassifiedReceipt,
    EngineFindings,
    ReceiptInput,
    RuleSet,
)
from expense_validator.domain.retriever import retrieve
from expense_validator.domain.taxonomy import restricted_for
from expense_validator.paths import CLASSIFICATIONS_FILE, REPO_ROOT

FIXTURES = REPO_ROOT / "tests" / "engine_cases" / "fixtures" / "engine_cases.jsonl"
OUT = REPO_ROOT / "explorations" / "results" / "iter2" / "RET" / "check.json"
ALL_RULES = RuleSet(rule_ids=tuple(sorted(REGISTRY)))
FIXTURE_SOURCE = ClassificationSource(
    classifier="fixture",
    model_id="hand-written",
    provider_endpoint="none",
    prompt_version="fixture",
    cache_key="fixture",
    request_id=None,
    cost_usd=None,
    prompt_tokens=None,
    completion_tokens=None,
    cache_hit=True,
)

Retriever = Callable[[ClassifiedReceipt], RuleSet]


def _outcome(findings: EngineFindings) -> dict[str, Any]:
    return {
        "disposition": findings.disposition,
        "exceptions": sorted(
            [e.rule_id, e.severity, list(e.line_ids)] for e in findings.exceptions
        ),
        "review_signals": sorted([s.rule_id, list(s.line_ids)] for s in findings.review_signals),
    }


def compare(
    batch: Sequence[ClassifiedReceipt], settings: Settings, retriever: Retriever = retrieve
) -> dict[str, Any]:
    """Evaluate each receipt of one batch (one cross-receipt context) under both rule sets."""
    context = build_context(list(batch), settings)
    details = []
    for cr in batch:
        mapped = _outcome(evaluate(cr, context, retriever(cr), settings))
        everything = _outcome(evaluate(cr, context, ALL_RULES, settings))
        if mapped != everything:
            details.append(
                {
                    "receipt_id": cr.receipt.receipt_id,
                    "trigger_map": mapped,
                    "all_rules": everything,
                }
            )
    return {"cases": len(batch), "differences": len(details), "details": details}


def _fixture_batches() -> list[tuple[str, list[ClassifiedReceipt]]]:
    batches = []
    for line in FIXTURES.read_text(encoding="utf-8").splitlines():
        if not line:
            continue
        case = json.loads(line)
        batch = []
        for entry in case["receipts"]:
            receipt = ReceiptInput.model_validate(entry["receipt"])
            classifications = tuple(
                Classification.model_validate(
                    {
                        "line_id": c["line_id"],
                        "status": "classified",
                        "category": c["category"],
                        "restricted": restricted_for(c["category"]),
                        "confidence": c["confidence"],
                        "subtype": c["subtype"],
                        "recipient_kind": c["recipient_kind"],
                        "recipient_name": c["recipient_name"],
                        "unclassified_reason": None,
                        "source": FIXTURE_SOURCE,
                    }
                )
                for c in entry["classifications"]
            )
            batch.append(ClassifiedReceipt(receipt=receipt, classifications=classifications))
        batches.append((case["case_id"], batch))
    return batches


def _receipt_batch() -> list[ClassifiedReceipt]:
    tracer = NoopTracer()
    classifier = OpenRouterClassifier(
        ClassificationCache(CLASSIFICATIONS_FILE), tracer, offline=True
    )
    receipts = sorted(load_receipts(), key=lambda r: r.receipt_id)
    return [classify_receipt(r, classifier, tracer, "retriever-check") for r in receipts]


def main() -> int:
    settings = load_settings()
    parts = [("fixture:" + cid, compare(b, settings)) for cid, b in _fixture_batches()]
    parts.append(("receipts", compare(_receipt_batch(), settings)))
    result = {
        "cases": sum(p["cases"] for _, p in parts),
        "differences": sum(p["differences"] for _, p in parts),
        "groups": [{"group": name, "cases": p["cases"]} for name, p in parts],
        "details": [d for _, p in parts for d in p["details"]],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"{result['cases']} cases, {result['differences']} differences -> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
