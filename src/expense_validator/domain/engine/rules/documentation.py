"""receipt-documentation-requirements.md: DOC-01 to DOC-04. All cite no line items."""

from __future__ import annotations

from decimal import Decimal

from expense_validator.domain.engine.base import Hit, Rule, RuleInput, money
from expense_validator.domain.engine.context import total_usd

DOC_01_LIMIT_USD = Decimal("75")
COVERS: dict[str, frozenset[str]] = {
    "Meals - Individual": frozenset({"food_beverage", "alcohol"}),
    "Meals - Team": frozenset({"food_beverage", "alcohol"}),
    "Client Entertainment": frozenset({"food_beverage", "alcohol"}),
    "Client Gifts": frozenset({"gift", "gift_card", "jewelry"}),
    "Lodging": frozenset({"lodging", "ground_transport", "laundry_service"}),
    "Travel - Other": frozenset(
        {"laundry_service", "health_otc", "ground_transport", "clothing", "personal_care"}
    ),
    "Office Supplies": frozenset({"office_supplies", "computer_accessory"}),
    "Computer Equipment": frozenset(
        {"computer_accessory", "personal_electronics", "software_subscription"}
    ),
    "Software": frozenset({"software_subscription"}),
}
DOC_03_IGNORED = frozenset({"service_fee", "other"})


def doc_01(inp: RuleInput) -> list[Hit]:
    total = total_usd(inp.receipt)
    if inp.receipt.itemized or total is None or total <= DOC_01_LIMIT_USD:
        return []
    return [
        Hit("DOC-01", computed={"total_usd": money(total), "limit_usd": money(DOC_01_LIMIT_USD)})
    ]


def doc_02(inp: RuleInput) -> list[Hit]:
    r = inp.receipt
    missing = [
        name
        for name, value in (
            ("merchant name", (r.merchant_name or "").strip() or None),
            ("transaction date", r.transaction_datetime),
            ("total", r.total_amount),
        )
        if value is None
    ]
    return [Hit("DOC-02", computed={"missing": ", ".join(missing)})] if missing else []


def doc_03(inp: RuleInput) -> list[Hit]:
    covered = COVERS.get(inp.receipt.submitted_expense_type)
    if covered is None:
        return []
    considered = [line for line in inp.lines if line.category not in DOC_03_IGNORED]
    if not considered or any(line.category in covered for line in considered):
        return []
    categories = sorted({line.category for line in considered})
    return [
        Hit(
            "DOC-03",
            computed={
                "declared_type": inp.receipt.submitted_expense_type,
                "line_categories": ", ".join(categories),
            },
        )
    ]


def doc_04(inp: RuleInput) -> list[Hit]:
    r = inp.receipt
    if r.currency == "USD":
        return []
    missing = [
        name
        for name, value in (("currency", r.currency), ("conversion rate", r.fx_rate_to_usd))
        if value is None
    ]
    return [Hit("DOC-04", computed={"missing": ", ".join(missing)})] if missing else []


RULES: dict[str, Rule] = {"DOC-01": doc_01, "DOC-02": doc_02, "DOC-03": doc_03, "DOC-04": doc_04}
