"""regional-addendum.md: REG-01..05. Regional rules override the global ones (FR-015).

REG-05 raises nothing: it fixes which rate converts, applied in engine/fx.py (A1). When a euro
rate needed by REG-03 or REG-04 is not on record, that rule cannot be evaluated: the receipt gets
a review signal under the rule's ID, never a pass.
"""

from __future__ import annotations

from decimal import Decimal

from expense_validator.engine import fx
from expense_validator.engine.base import Hit, Rule, RuleInput, line_ids, money
from expense_validator.engine.context import total_usd
from expense_validator.engine.rules.meals import day_total, meal_day

APAC_CAP_USD = Decimal("60")
EMEA_CAP_EUR = Decimal("70")
VAT_THRESHOLD_EUR = Decimal("50")


def reg_01(inp: RuleInput) -> list[Hit]:
    alcohol = inp.of("alcohol")
    if inp.receipt.entity != "APAC" or not alcohol:
        return []
    return [Hit("REG-01", line_ids(alcohol))]


def reg_02(inp: RuleInput) -> list[Hit]:
    if inp.receipt.entity != "APAC":
        return []
    day = meal_day(inp)
    total = day_total(day)
    if not day or total <= APAC_CAP_USD:
        return []
    return [
        Hit(
            "REG-02",
            computed={"day_per_person_usd": money(total), "cap_usd": money(APAC_CAP_USD)},
        )
    ]


def reg_03(inp: RuleInput) -> list[Hit]:
    if inp.receipt.entity != "EMEA":
        return []
    day = meal_day(inp)
    if not day:
        return []
    cap = fx.eur_threshold_usd(EMEA_CAP_EUR, inp.receipt, inp.settings)
    if cap is None:
        return [Hit("REG-03", computed={"euro_rate": "not on record"}, as_signal=True)]
    total = day_total(day)
    if total <= cap:
        return []
    return [
        Hit(
            "REG-03",
            computed={
                "day_per_person_usd": money(total),
                "cap_eur": money(EMEA_CAP_EUR),
                "cap_usd": money(cap),
            },
        )
    ]


def reg_04(inp: RuleInput) -> list[Hit]:
    r = inp.receipt
    if r.entity != "EMEA" or r.vat_number:
        return []
    if r.currency == "EUR" and r.total_amount is not None:
        total_eur = r.total_amount
    else:
        usd = total_usd(r)
        rate = fx.eur_to_usd(r, inp.settings)
        if usd is None or rate is None:
            return [Hit("REG-04", computed={"euro_rate": "not on record"}, as_signal=True)]
        total_eur = usd / rate
    if total_eur <= VAT_THRESHOLD_EUR:
        return []
    return [
        Hit(
            "REG-04",
            computed={
                "total_eur": money(total_eur),
                "threshold_eur": money(VAT_THRESHOLD_EUR),
                "vat_number": "not recorded",
            },
        )
    ]


RULES: dict[str, Rule] = {"REG-01": reg_01, "REG-02": reg_02, "REG-03": reg_03, "REG-04": reg_04}
