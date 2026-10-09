"""Cross-receipt context: aggregates that span receipts, built once per batch (FR-021).

- meal days: per employee and calendar date, each meal receipt's per-person meal spend (MEAL-01,
  REG-02, REG-03 definitions);
- trip OTC: per trip, the OTC medication total in USD (HEALTH-01, A4).

Uncertain items are excluded (EXC-03). The result does not depend on the order of receipts.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal

from expense_validator.engine import fx
from expense_validator.engine.base import Line
from expense_validator.engine.settings import Settings
from expense_validator.engine.uncertainty import split_lines
from expense_validator.models import (
    ClassifiedReceipt,
    CrossReceiptContext,
    MealContribution,
    ReceiptInput,
)

MEAL_TYPES = frozenset({"Meals - Individual", "Meals - Team", "Client Entertainment"})
MEAL_SPEND_CATEGORIES = frozenset({"food_beverage", "alcohol", "service_fee"})
FOOD_OR_DRINK = frozenset({"food_beverage", "alcohol"})


def day_key(employee_id: str, when: datetime) -> str:
    return f"{employee_id}|{when.date().isoformat()}"


def total_usd(receipt: ReceiptInput) -> Decimal | None:
    if receipt.total_amount is not None:
        converted = fx.to_usd(receipt.total_amount, receipt)
        if converted is not None:
            return converted
    return receipt.total_amount_usd


def is_meal_receipt(receipt: ReceiptInput, lines: Sequence[Line]) -> bool:
    """MEAL-01: declared as a meal type and containing food or drink, or not itemized."""
    if receipt.submitted_expense_type not in MEAL_TYPES:
        return False
    return not receipt.itemized or any(line.category in FOOD_OR_DRINK for line in lines)


def meal_spend_usd(receipt: ReceiptInput, lines: Sequence[Line]) -> Decimal:
    if not receipt.itemized:
        return total_usd(receipt) or Decimal("0")
    return sum(
        (line.amount_usd for line in lines if line.category in MEAL_SPEND_CATEGORIES),
        Decimal("0"),
    )


def is_international(receipt: ReceiptInput, settings: Settings) -> bool:
    """A8: the receipt currency differs from the currency of the employee's home country."""
    home = settings.home_currency.get(receipt.employee_country)
    return receipt.currency is not None and home is not None and receipt.currency != home


def _cap_basis(receipt: ReceiptInput) -> str:
    return {"APAC": "apac", "EMEA": "emea"}.get(receipt.entity, "global")


def build_context(batch: Sequence[ClassifiedReceipt], settings: Settings) -> CrossReceiptContext:
    meal_days: dict[str, list[MealContribution]] = {}
    trip_otc: dict[str, Decimal] = {}
    for cr in batch:
        receipt = cr.receipt
        lines, _ = split_lines(cr, settings)
        if receipt.transaction_datetime is not None and is_meal_receipt(receipt, lines):
            spend = meal_spend_usd(receipt, lines)
            meal_days.setdefault(day_key(receipt.employee_id, receipt.transaction_datetime), [])
            meal_days[day_key(receipt.employee_id, receipt.transaction_datetime)].append(
                MealContribution(
                    receipt_id=receipt.receipt_id,
                    per_person_usd=spend / (receipt.attendee_count or 1),
                    international=is_international(receipt, settings),
                    cap_basis=_cap_basis(receipt),
                    eur_rate_to_usd=fx.eur_to_usd(receipt, settings)
                    if receipt.entity == "EMEA"
                    else None,
                )
            )
        otc = [line.amount_usd for line in lines if line.category == "health_otc"]
        if receipt.trip_id is not None and otc:
            trip_otc[receipt.trip_id] = trip_otc.get(receipt.trip_id, Decimal("0")) + sum(
                otc, Decimal("0")
            )
    return CrossReceiptContext(
        meal_days={
            key: tuple(sorted(meal_days[key], key=lambda c: c.receipt_id))
            for key in sorted(meal_days)
        },
        trip_otc_usd={trip: trip_otc[trip] for trip in sorted(trip_otc)},
    )
