"""meals-and-entertainment-policy.md: MEAL-01, MEAL-02, ALC-01..03, ENT-01, ENT-02.

For APAC employees REG-01 replaces ALC-01..03 and REG-02 replaces MEAL-01; for EMEA employees
REG-03 replaces MEAL-01 (regional-addendum.md). Those overrides are applied here by entity.
"""

from __future__ import annotations

from decimal import Decimal

from expense_validator.domain.engine.base import Hit, Rule, RuleInput, line_ids, money
from expense_validator.domain.engine.context import day_key, is_meal_receipt, total_usd
from expense_validator.domain.engine.rules.merchant import ON_PREMISES_MCC
from expense_validator.domain.models import MealContribution

DOMESTIC_CAP_USD = Decimal("75")
INTERNATIONAL_CAP_USD = Decimal("100")
MEAL_02_LIMIT_USD = Decimal("150")
ALC_02_CAP_PER_ATTENDEE_USD = Decimal("30")


def meal_day(inp: RuleInput) -> tuple[MealContribution, ...]:
    """This receipt's employee-day of meal receipts, or () if it is not a meal receipt."""
    r = inp.receipt
    if r.transaction_datetime is None or not is_meal_receipt(r, inp.lines):
        return ()
    return inp.context.meal_days.get(day_key(r.employee_id, r.transaction_datetime), ())


def day_total(day: tuple[MealContribution, ...]) -> Decimal:
    return sum((c.per_person_usd for c in day), Decimal("0"))


def meal_01(inp: RuleInput) -> list[Hit]:
    if inp.receipt.entity != "GLOBAL":
        return []
    day = meal_day(inp)
    if not day:
        return []
    cap = INTERNATIONAL_CAP_USD if any(c.international for c in day) else DOMESTIC_CAP_USD
    total = day_total(day)
    if total <= cap:
        return []
    return [
        Hit(
            "MEAL-01",
            computed={
                "day_per_person_usd": money(total),
                "cap_usd": money(cap),
                "receipts_that_day": str(len(day)),
            },
        )
    ]


def meal_02(inp: RuleInput) -> list[Hit]:
    r = inp.receipt
    total = total_usd(r)
    if not is_meal_receipt(r, inp.lines) or r.attendee_count is not None or total is None:
        return []
    if total <= MEAL_02_LIMIT_USD:
        return []
    return [Hit("MEAL-02", computed={"total_usd": money(total), "limit_usd": "150.00"})]


def _alcohol_permitted(inp: RuleInput) -> bool:
    r = inp.receipt
    return r.submitted_expense_type == "Client Entertainment" and (r.attendee_count or 0) >= 2


def alc_01(inp: RuleInput) -> list[Hit]:
    alcohol = inp.of("alcohol")
    if inp.receipt.entity == "APAC" or not alcohol or inp.receipt.mcc not in ON_PREMISES_MCC:
        return []
    if _alcohol_permitted(inp):
        return []
    return [Hit("ALC-01", line_ids(alcohol))]


def alc_02(inp: RuleInput) -> list[Hit]:
    alcohol = inp.of("alcohol")
    r = inp.receipt
    if r.entity == "APAC" or not alcohol or r.mcc not in ON_PREMISES_MCC:
        return []
    if not _alcohol_permitted(inp) or not r.attendee_count:
        return []
    per_attendee = sum((line.amount_usd for line in alcohol), Decimal("0")) / r.attendee_count
    if per_attendee <= ALC_02_CAP_PER_ATTENDEE_USD:
        return []
    return [
        Hit(
            "ALC-02",
            line_ids(alcohol),
            {
                "alcohol_per_attendee_usd": money(per_attendee),
                "cap_usd": money(ALC_02_CAP_PER_ATTENDEE_USD),
                "attendees": str(r.attendee_count),
            },
        )
    ]


def alc_03(inp: RuleInput) -> list[Hit]:
    alcohol = inp.of("alcohol")
    if inp.receipt.entity == "APAC" or not alcohol or inp.receipt.mcc in ON_PREMISES_MCC:
        return []
    return [Hit("ALC-03", line_ids(alcohol), {"mcc": str(inp.receipt.mcc)})]


def ent_01(inp: RuleInput) -> list[Hit]:
    """Venue spend needs a VP approval; no prefix maps to one (A5), so PA- never satisfies."""
    tickets = [line for line in inp.of("other") if line.subtype == "event_ticket"]
    if not tickets or inp.reference_kind() == "vp_approval":
        return []
    return [Hit("ENT-01", line_ids(tickets))]


def ent_02(inp: RuleInput) -> list[Hit]:
    lines = inp.of("gambling")
    return [Hit("ENT-02", line_ids(lines))] if lines else []


RULES: dict[str, Rule] = {
    "MEAL-01": meal_01,
    "MEAL-02": meal_02,
    "ALC-01": alc_01,
    "ALC-02": alc_02,
    "ALC-03": alc_03,
    "ENT-01": ent_01,
    "ENT-02": ent_02,
}
