"""non-reimbursable-items.md: PERS-01..03, HOUSE-01, HEALTH-01, LAUNDRY-01 (A4, A5, A6)."""

from __future__ import annotations

from decimal import Decimal

from expense_validator.domain.engine.base import Hit, Rule, RuleInput, line_ids, money

BAGGAGE_ALLOWANCE_USD = Decimal("150")
OTC_TRIP_LIMIT_USD = Decimal("25")
LAUNDRY_MIN_NIGHTS = 4


def _baggage_carve_out(inp: RuleInput) -> bool:
    """One $150 allowance per baggage delay, shared by toiletries and clothing (PERS-01/02).
    It needs a baggage-delay reference; no prefix maps to one in this dataset (A5)."""
    if inp.reference_kind() != "baggage_delay":
        return False
    spend = sum((line.amount_usd for line in inp.of("personal_care", "clothing")), Decimal("0"))
    return spend <= BAGGAGE_ALLOWANCE_USD


def pers_01(inp: RuleInput) -> list[Hit]:
    lines = inp.of("personal_care")
    return [Hit("PERS-01", line_ids(lines))] if lines and not _baggage_carve_out(inp) else []


def pers_02(inp: RuleInput) -> list[Hit]:
    lines = inp.of("clothing")
    return [Hit("PERS-02", line_ids(lines))] if lines and not _baggage_carve_out(inp) else []


def pers_03(inp: RuleInput) -> list[Hit]:
    lines = inp.of("tobacco")
    return [Hit("PERS-03", line_ids(lines))] if lines else []


def house_01(inp: RuleInput) -> list[Hit]:
    lines = inp.of("household_goods")
    return [Hit("HOUSE-01", line_ids(lines))] if lines else []


def health_01(inp: RuleInput) -> list[Hit]:
    """OTC: low without a trip, or when the trip's total across receipts exceeds $25 (A4).
    Prescription medication (subtype, A6): always medium."""
    hits: list[Hit] = []
    rx = [line for line in inp.of("other") if line.subtype == "prescription_medication"]
    if rx:
        hits.append(Hit("HEALTH-01", line_ids(rx), severity="medium", variant="prescription"))
    otc = inp.of("health_otc")
    trip = inp.receipt.trip_id
    if otc and trip is None:
        hits.append(Hit("HEALTH-01", line_ids(otc), {"trip": "none"}))
    elif otc and trip is not None:
        total = inp.context.trip_otc_usd.get(trip, Decimal("0"))
        if total > OTC_TRIP_LIMIT_USD:
            hits.append(
                Hit(
                    "HEALTH-01",
                    line_ids(otc),
                    {"trip_otc_total_usd": money(total), "limit_usd": money(OTC_TRIP_LIMIT_USD)},
                )
            )
    return hits


def laundry_01(inp: RuleInput) -> list[Hit]:
    lines = inp.of("laundry_service")
    nights = inp.receipt.trip_nights
    if not lines or (inp.receipt.trip_id is not None and (nights or 0) >= LAUNDRY_MIN_NIGHTS):
        return []
    trip = "none" if inp.receipt.trip_id is None else str(nights)
    return [Hit("LAUNDRY-01", line_ids(lines), {"trip_nights": trip, "minimum_nights": "4"})]


RULES: dict[str, Rule] = {
    "PERS-01": pers_01,
    "PERS-02": pers_02,
    "PERS-03": pers_03,
    "HOUSE-01": house_01,
    "HEALTH-01": health_01,
    "LAUNDRY-01": laundry_01,
}
