"""Orchestration: load → normalise → classify → context → retrieve, evaluate, report.

ADR 0002 flow. Receipts are processed in receipt_id order and written canonically, so the
output is byte-identical for the same inputs, cache, prompt, model and rules (research R9).
Each receipt has one trace with two top-level spans: `validate-receipt` (normalise, classify)
and `decide-receipt` (retrieve, apply, report). Deciding needs every receipt classified first,
because the cross-receipt context spans receipts.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

from expense_validator.classification.port import ItemClassifier, build_request
from expense_validator.engine.context import build_context
from expense_validator.engine.evaluate import evaluate
from expense_validator.engine.registry import rules_version
from expense_validator.engine.settings import Settings
from expense_validator.models import (
    ClassifiedReceipt,
    ReceiptInput,
    ReceiptResult,
    RunMetadata,
)
from expense_validator.normaliser import normalise
from expense_validator.reporter import report
from expense_validator.retriever import retrieve
from expense_validator.tracing import Tracer


def run_metadata(classifier: ItemClassifier, settings: Settings) -> RunMetadata:
    return RunMetadata(
        classifier=classifier.name,
        model_id=classifier.model_id,
        provider_endpoint=classifier.provider_endpoint,
        prompt_version=classifier.prompt_version,
        rules_version=rules_version(),
        exc03_threshold=float(settings.exc03_threshold),
        exc03_threshold_status="provisional",
    )


def classify_receipt(
    receipt: ReceiptInput, classifier: ItemClassifier, tracer: Tracer, run_label: str
) -> ClassifiedReceipt:
    with tracer.receipt_trace(
        receipt.receipt_id, run_label, input=receipt.model_dump(mode="json")
    ) as root:
        with tracer.span("normalise-receipt") as span:
            items = normalise(receipt)
            span.update(output=[i.model_dump(mode="json") for i in items])
        with tracer.span("classify-receipt") as span:
            classifications = tuple(
                classifier.classify(i.line_id, build_request(receipt, i)) for i in items
            )
            span.update(
                output=[
                    {
                        "line_id": c.line_id,
                        "status": c.status,
                        "category": c.category,
                        "confidence": c.confidence,
                        "cache_hit": c.source.cache_hit,
                        "cache_key": c.source.cache_key,
                        "request_id": c.source.request_id,
                        "unclassified_reason": c.unclassified_reason,
                    }
                    for c in classifications
                ]
            )
        root.update(output={"classified_lines": len(classifications)})
    return ClassifiedReceipt(receipt=receipt, classifications=classifications)


def run_pipeline(
    receipts: Sequence[ReceiptInput],
    classifier: ItemClassifier,
    tracer: Tracer,
    settings: Settings,
    run_label: str,
) -> list[ReceiptResult]:
    ordered = sorted(receipts, key=lambda r: r.receipt_id)
    classified = [classify_receipt(r, classifier, tracer, run_label) for r in ordered]
    context = build_context(classified, settings)
    meta = run_metadata(classifier, settings)
    results: list[ReceiptResult] = []
    for cr in classified:
        with tracer.receipt_trace(
            cr.receipt.receipt_id, run_label, input=None, name="decide-receipt"
        ) as root:
            with tracer.span("retrieve-rules") as span:
                ruleset = retrieve(cr)
                span.update(output=list(ruleset.rule_ids))
            with tracer.span("apply-rules", input=list(ruleset.rule_ids)) as span:
                findings = evaluate(cr, context, ruleset, settings)
                span.update(output=findings.model_dump(mode="json"))
            with tracer.span("report-exceptions") as span:
                result = report(cr, findings, meta)
                span.update(output=[e.explanation for e in result.exceptions])
            root.update(output=result.model_dump(mode="json"))
        results.append(result)
    return results


def write_results(path: Path, results: Sequence[ReceiptResult]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(r.model_dump(mode="json"), ensure_ascii=False) for r in results]
    path.write_text("".join(line + "\n" for line in lines), encoding="utf-8")
