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


def _simple(rule_id: str, sentence: str) -> ExceptionTemplate:
    return lambda f, r: f"{rule_id}: {_lines(f.line_ids)} {sentence}"


def _tech_02(f: ExceptionFinding, r: ClassifiedReceipt) -> str:
    c = f.computed
    return (
        f"TECH-02: {_lines(f.line_ids)} has a unit price of ${c['unit_price_usd']}, above the "
        f"${c['cap_usd']} per-item limit, and no pre-approval reference is recorded."
    )


def _meal_01(f: ExceptionFinding, r: ClassifiedReceipt) -> str:
    c = f.computed
    return (
        f"MEAL-01: {_lines(f.line_ids)}: this employee's meal spend that day is "
        f"${c['day_per_person_usd']} per person across {c['receipts_that_day']} meal receipt(s), "
        f"above the ${c['cap_usd']} daily cap."
    )


def _meal_02(f: ExceptionFinding, r: ClassifiedReceipt) -> str:
    c = f.computed
    return (
        f"MEAL-02: {_lines(f.line_ids)}: the meal receipt total is ${c['total_usd']}, above "
        f"${c['limit_usd']}, and no attendee count is recorded."
    )


def _alc_02(f: ExceptionFinding, r: ClassifiedReceipt) -> str:
    c = f.computed
    return (
        f"ALC-02: {_lines(f.line_ids)}: alcohol comes to ${c['alcohol_per_attendee_usd']} per "
        f"attendee across {c['attendees']} attendees, above the ${c['cap_usd']} cap."
    )


def _alc_03(f: ExceptionFinding, r: ClassifiedReceipt) -> str:
    return (
        f"ALC-03: {_lines(f.line_ids)} is alcohol bought at MCC {f.computed['mcc']}, which is not "
        "a restaurant, bar or hotel, so it is retail alcohol."
    )


def _gift_01(f: ExceptionFinding, r: ClassifiedReceipt) -> str:
    parts = []
    c = f.computed
    if "unnamed_gifts_at_or_above_usd" in c:
        parts.append(
            f"a gift of ${c['unnamed_gifts_at_or_above_usd']} or more does not name its recipient"
        )
    if f.evidence.startswith("Gifts to clients"):
        parts.append(f"gifts to one recipient total more than ${c['cap_per_recipient_usd']}")
    return f"GIFT-01: {_lines(f.line_ids)}: " + "; ".join(parts) + "."


def _health_01(f: ExceptionFinding, r: ClassifiedReceipt) -> str:
    c = f.computed
    if f.severity == "medium":
        return f"HEALTH-01: {_lines(f.line_ids)} is prescription medication, never reimbursable."
    if c.get("trip") == "none":
        return (
            f"HEALTH-01: {_lines(f.line_ids)} is OTC medication on a receipt with no trip record."
        )
    return (
        f"HEALTH-01: {_lines(f.line_ids)}: OTC medication on this trip totals "
        f"${c['trip_otc_total_usd']} across its receipts, above the ${c['limit_usd']} limit."
    )


def _laundry_01(f: ExceptionFinding, r: ClassifiedReceipt) -> str:
    nights = f.computed["trip_nights"]
    trip = "no trip record" if nights == "none" else f"a trip of {nights} night(s)"
    return (
        f"LAUNDRY-01: {_lines(f.line_ids)} is laundry on {trip}; it is reimbursable only on trips "
        "of four or more nights."
    )


def _receipt_rule(rule_id: str, sentence: Callable[[dict[str, str]], str]) -> ExceptionTemplate:
    return lambda f, r: f"{rule_id}: {_lines(f.line_ids)}: {sentence(f.computed)}"


EXCEPTION_TEMPLATES: dict[str, ExceptionTemplate] = {
    "MEAL-01": _meal_01,
    "MEAL-02": _meal_02,
    "ALC-01": _simple(
        "ALC-01",
        "is alcohol on a receipt that is not Client Entertainment with an attendee count of two "
        "or more.",
    ),
    "ALC-02": _alc_02,
    "ALC-03": _alc_03,
    "ENT-01": _simple(
        "ENT-01",
        "is venue or event spend and no VP approval reference is recorded (a PA- reference is a "
        "pre-approval, decision A5).",
    ),
    "ENT-02": _simple("ENT-02", "is gambling spend, which is prohibited."),
    "TECH-01": _simple("TECH-01", "is personal electronics, not reimbursable."),
    "TECH-02": _tech_02,
    "TECH-03": _simple("TECH-03", "is mobile phone hardware, procured centrally by IT."),
    "TECH-04": _simple(
        "TECH-04",
        "is a software subscription and no manager approval reference is recorded (a PA- "
        "reference is a pre-approval, decision A5).",
    ),
    "GIFT-01": _gift_01,
    "GIFT-02": _simple("GIFT-02", "is a gift card or cash equivalent, never reimbursable."),
    "GIFT-03": _simple(
        "GIFT-03", "is a gift for an employee, which must go through HR (decision A9)."
    ),
    "GIFT-04": _simple(
        "GIFT-04",
        "is something of value provided to a government official, prohibited at any amount and "
        "routed to Compliance (decision A9).",
    ),
    "PERS-01": _simple("PERS-01", "is personal care, and no baggage-delay reference is recorded."),
    "PERS-02": _simple(
        "PERS-02", "is clothing or footwear, and no baggage-delay reference is recorded."
    ),
    "PERS-03": _simple("PERS-03", "is tobacco or vaping, not reimbursable."),
    "HOUSE-01": _simple("HOUSE-01", "is a household good, not reimbursable."),
    "HEALTH-01": _health_01,
    "LAUNDRY-01": _laundry_01,
    "MCC-01": _receipt_rule(
        "MCC-01", lambda c: f"MCC {c['mcc']} is a high-risk merchant category."
    ),
    "DOC-01": _receipt_rule(
        "DOC-01",
        lambda c: (
            f"the total is ${c['total_usd']}, above ${c['limit_usd']}, and the receipt is "
            "not itemized."
        ),
    ),
    "DOC-02": _receipt_rule("DOC-02", lambda c: f"the receipt does not show its {c['missing']}."),
    "DOC-03": _receipt_rule(
        "DOC-03",
        lambda c: (
            f"no line belongs to a category that '{c['declared_type']}' covers (lines are "
            f"{c['line_categories']})."
        ),
    ),
    "DOC-04": _receipt_rule(
        "DOC-04", lambda c: f"the foreign-currency receipt does not record its {c['missing']}."
    ),
    "REG-01": _simple("REG-01", "is alcohol, never reimbursable for APAC-entity employees."),
    "REG-02": _receipt_rule(
        "REG-02",
        lambda c: (
            f"this employee's meal spend that day is ${c['day_per_person_usd']} per "
            f"person, above the APAC cap of ${c['cap_usd']}."
        ),
    ),
    "REG-03": _receipt_rule(
        "REG-03",
        lambda c: (
            f"this employee's meal spend that day is ${c['day_per_person_usd']} per "
            f"person, above the EMEA cap of EUR {c['cap_eur']} (${c['cap_usd']} at the euro rate "
            "on the transaction date)."
        ),
    ),
    "REG-04": _receipt_rule(
        "REG-04",
        lambda c: (
            f"the total is EUR {c['total_eur']}, above EUR {c['threshold_eur']}, and no "
            "VAT number is recorded (decision A2)."
        ),
    ),
}


def _mcc_02(s: ReviewSignal, r: ClassifiedReceipt) -> str:
    receipt = r.receipt
    return (
        f"MCC {receipt.mcc} ({receipt.mcc_description}) is a medium-risk merchant category; "
        "context only, not an exception."
    )


def _exc_03(s: ReviewSignal, r: ClassifiedReceipt) -> str:
    by_line = {c.line_id: c for c in r.classifications}
    parts = []
    for line_id in s.line_ids:
        c = by_line[line_id]
        if c.status == "unclassified":
            parts.append(f"{line_id} could not be classified ({c.unclassified_reason})")
        else:
            parts.append(f"{line_id} has confidence {c.confidence:.2f}")
    return (
        "Category uncertain, so these lines are left out of every other rule: "
        + "; ".join(parts)
        + "."
    )


def _euro_rate_missing(s: ReviewSignal, r: ClassifiedReceipt) -> str:
    return (
        f"{s.rule_id} could not be evaluated: the euro rate on the transaction date is not on "
        "record (decision A1), so the receipt goes to review."
    )


def _generic_signal(s: ReviewSignal, r: ClassifiedReceipt) -> str:
    return f"{s.rule_id} review signal on {_lines(s.line_ids)}."


SIGNAL_TEMPLATES: dict[str, SignalTemplate] = {
    "MCC-02": _mcc_02,
    "EXC-03": _exc_03,
    "REG-03": _euro_rate_missing,
    "REG-04": _euro_rate_missing,
}


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
