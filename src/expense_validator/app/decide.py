"""The decision step: retrieve, apply rules, report (ADR 0002 flow, ADR 0007 D2).

One function, called by the batch run and by the worker, so the two cannot diverge (FR-016).
It is deterministic: the same classified receipt, context and settings give the same result.
"""

from __future__ import annotations

from typing import Any

from expense_validator.domain.engine.evaluate import evaluate
from expense_validator.domain.engine.settings import Settings
from expense_validator.domain.models import (
    ClassifiedReceipt,
    CrossReceiptContext,
    ReceiptResult,
    RunMetadata,
)
from expense_validator.domain.reporter import report
from expense_validator.domain.retriever import retrieve
from expense_validator.ports.tracer import Tracer


def _version_metadata(version: int | None) -> dict[str, Any]:
    """A stored evaluation version names itself on its decision, so that every decision of one
    receipt revision can sit in the same trace and still be told apart."""
    return {} if version is None else {"metadata": {"evaluation_version": version}}


def decide_receipt(
    classified: ClassifiedReceipt,
    context: CrossReceiptContext,
    meta: RunMetadata,
    settings: Settings,
    tracer: Tracer,
    run_label: str,
    version: int | None = None,
) -> ReceiptResult:
    with tracer.receipt_trace(
        classified.receipt.receipt_id, run_label, input=None, name="decide-receipt"
    ) as root:
        with tracer.span("retrieve-rules") as span:
            ruleset = retrieve(classified)
            span.update(output=list(ruleset.rule_ids))
        with tracer.span("apply-rules", input=list(ruleset.rule_ids)) as span:
            findings = evaluate(classified, context, ruleset, settings)
            span.update(output=findings.model_dump(mode="json"))
        with tracer.span("report-exceptions") as span:
            result = report(classified, findings, meta)
            span.update(output=[e.explanation for e in result.exceptions])
        root.update(output=result.model_dump(mode="json"), **_version_metadata(version))
    return result
