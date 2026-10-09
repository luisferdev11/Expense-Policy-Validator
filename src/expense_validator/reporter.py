"""Exception reporter: deterministic templates over the engine's findings (FR-022).

An explanation states the rule, the lines involved and the arithmetic in `computed`. It never
adds a claim the engine did not compute: every number comes from `computed` or the receipt's
own recorded fields.
"""

from __future__ import annotations

from collections.abc import Callable

from expense_validator.models import (
    ClassifiedReceipt,
    EngineFindings,
    ExceptionFinding,
    OutputLineItem,
    ReceiptResult,
    ReviewSignal,
    RunMetadata,
)

ExceptionTemplate = Callable[[ExceptionFinding, ClassifiedReceipt], str]
SignalTemplate = Callable[[ReviewSignal, ClassifiedReceipt], str]


def _lines(ids: list[str]) -> str:
    if not ids:
        return "the receipt as a whole"
    return ("line " if len(ids) == 1 else "lines ") + ", ".join(ids)


def _generic(f: ExceptionFinding, r: ClassifiedReceipt) -> str:
    facts = "; ".join(f"{k} = {v}" for k, v in f.computed.items())
    return f"{f.rule_id} applies to {_lines(f.line_ids)}." + (
        f" Computed: {facts}." if facts else ""
    )


def _tech_02(f: ExceptionFinding, r: ClassifiedReceipt) -> str:
    c = f.computed
    return (
        f"TECH-02: {_lines(f.line_ids)} has a unit price of ${c['unit_price_usd']}, above the "
        f"${c['cap_usd']} per-item limit, and no pre-approval reference is recorded."
    )


EXCEPTION_TEMPLATES: dict[str, ExceptionTemplate] = {"TECH-02": _tech_02}


def _mcc_02(s: ReviewSignal, r: ClassifiedReceipt) -> str:
    receipt = r.receipt
    return (
        f"MCC {receipt.mcc} ({receipt.mcc_description}) is a medium-risk merchant category; "
        "context only, not an exception."
    )


def _generic_signal(s: ReviewSignal, r: ClassifiedReceipt) -> str:
    return f"{s.rule_id} review signal on {_lines(s.line_ids)}."


SIGNAL_TEMPLATES: dict[str, SignalTemplate] = {"MCC-02": _mcc_02}


def _output_lines(r: ClassifiedReceipt) -> list[OutputLineItem]:
    return [
        OutputLineItem(
            line_id=item.line_id,
            description_raw=item.description_raw,
            category=c.category,
            restricted=c.restricted,
            confidence=c.confidence,
            subtype=c.subtype,
            recipient_kind=c.recipient_kind,
            recipient_name=c.recipient_name,
            status=c.status,
            unclassified_reason=c.unclassified_reason,
        )
        for item, c in zip(r.receipt.line_items, r.classifications, strict=True)
    ]


def report(r: ClassifiedReceipt, findings: EngineFindings, run: RunMetadata) -> ReceiptResult:
    exceptions = [
        f.model_copy(update={"explanation": EXCEPTION_TEMPLATES.get(f.rule_id, _generic)(f, r)})
        for f in findings.exceptions
    ]
    signals = [
        s.model_copy(update={"reason": SIGNAL_TEMPLATES.get(s.rule_id, _generic_signal)(s, r)})
        for s in findings.review_signals
    ]
    return ReceiptResult(
        receipt_id=r.receipt.receipt_id,
        disposition=findings.disposition,
        line_items=_output_lines(r),
        exceptions=exceptions,
        review_signals=signals,
        run=run,
    )
