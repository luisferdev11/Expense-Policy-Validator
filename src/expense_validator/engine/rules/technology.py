"""technology-and-equipment-policy.md: TECH-01 to TECH-04 (A5 reference kinds, A6 subtype)."""

from __future__ import annotations

from decimal import Decimal

from expense_validator.engine.base import Hit, Rule, RuleInput, money
from expense_validator.engine.base import line_ids as _ids

TECH_02_CAP_USD = Decimal("200")


def tech_01(inp: RuleInput) -> list[Hit]:
    lines = inp.of("personal_electronics")
    return [Hit("TECH-01", _ids(lines))] if lines else []


def tech_02(inp: RuleInput) -> list[Hit]:
    """Accessories above $200 per item, judged on unit price in USD, need a pre-approval."""
    if inp.reference_kind() == "pre_approval":
        return []
    over = [line for line in inp.of("computer_accessory") if line.unit_price_usd > TECH_02_CAP_USD]
    if not over:
        return []
    top = max(line.unit_price_usd for line in over)
    return [
        Hit(
            "TECH-02",
            _ids(over),
            {"unit_price_usd": money(top), "cap_usd": money(TECH_02_CAP_USD)},
        )
    ]


def tech_03(inp: RuleInput) -> list[Hit]:
    lines = [line for line in inp.of("other") if line.subtype == "mobile_handset"]
    return [Hit("TECH-03", _ids(lines))] if lines else []


def tech_04(inp: RuleInput) -> list[Hit]:
    """Software needs a manager approval; no prefix maps to one (A5), so PA- never satisfies."""
    if inp.reference_kind() == "manager_approval":
        return []
    lines = inp.of("software_subscription")
    return [Hit("TECH-04", _ids(lines))] if lines else []


RULES: dict[str, Rule] = {
    "TECH-01": tech_01,
    "TECH-02": tech_02,
    "TECH-03": tech_03,
    "TECH-04": tech_04,
}
