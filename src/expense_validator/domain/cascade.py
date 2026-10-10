"""Which receipts can a change to one receipt affect (ADR 0007 D6, research R4).

MEAL-01, REG-02 and REG-03 aggregate per employee and day, HEALTH-01 per trip. Two receipts can
influence each other only if they share one of those keys. The keys are a superset of what the
context actually uses (a receipt that is not a meal still shares a day key), which is safe: a
re-evaluation with an unchanged result records nothing (D7). The day key is the engine's own.
"""

from __future__ import annotations

from expense_validator.domain.engine.context import day_key
from expense_validator.domain.models import ReceiptInput


def sharing_keys(receipt: ReceiptInput) -> frozenset[str]:
    keys: set[str] = set()
    if receipt.transaction_datetime is not None:
        keys.add("day:" + day_key(receipt.employee_id, receipt.transaction_datetime))
    if receipt.trip_id is not None:
        keys.add("trip:" + receipt.trip_id)
    return frozenset(keys)
