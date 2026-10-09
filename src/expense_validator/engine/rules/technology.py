"""technology-and-equipment-policy.md: TECH-01 to TECH-04."""

from __future__ import annotations

from decimal import Decimal

from expense_validator.engine.base import Hit, Rule, RuleInput, money

TECH_02_CAP_USD = Decimal("200")


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
            tuple(line.line_id for line in over),
            {"unit_price_usd": money(top), "cap_usd": money(TECH_02_CAP_USD)},
        )
    ]


RULES: dict[str, Rule] = {"TECH-02": tech_02}
