"""Builders for synthetic receipts and classifications used across tests.

Every value here is invented for tests. Nothing is read from the answer fields.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from expense_validator.domain.models import (
    Classification,
    ClassificationSource,
    ClassifiedReceipt,
    LineItemInput,
    ReceiptInput,
)
from expense_validator.domain.taxonomy import restricted_for

D = Decimal


def item(
    n: int = 1,
    receipt_id: str = "SYN-1",
    description: str = "Item",
    amount: str = "10.00",
    quantity: str = "1",
    unit_price: str | None = None,
    fx: str = "1",
    language: str = "en",
) -> dict[str, Any]:
    qty = D(quantity)
    unit = D(unit_price) if unit_price is not None else D(amount) / qty
    return {
        "line_id": f"{receipt_id}-L{n}",
        "description_raw": description,
        "language": language,
        "quantity": qty,
        "unit_price": unit,
        "amount": D(amount),
        "amount_usd": (D(amount) * D(fx)).quantize(D("0.01")),
    }


def receipt(items: list[dict[str, Any]] | None = None, **overrides: Any) -> ReceiptInput:
    items = items if items is not None else [item()]
    rid = overrides.get("receipt_id", "SYN-1")
    fx_override = overrides.get("fx_rate_to_usd", "1")
    fx = D(str(fx_override)) if fx_override is not None else D("1")
    total = sum((D(str(i["amount"])) for i in items), D("0"))
    base: dict[str, Any] = {
        "receipt_id": rid,
        "employee_id": "E-1",
        "employee_country": "US",
        "entity": "GLOBAL",
        "submitted_expense_type": "Office Supplies",
        "merchant_name": "Synthetic Merchant",
        "mcc": 5943,
        "mcc_description": "Office and stationery supply",
        "transaction_datetime": "2026-05-01T12:00:00",
        "currency": "USD",
        "fx_rate_to_usd": fx,
        "total_amount": total,
        "total_amount_usd": (total * fx).quantize(D("0.01")),
        "attendee_count": None,
        "trip_id": None,
        "trip_nights": None,
        "pre_approval_ref": None,
        "itemized": True,
        "line_items": items,
    }
    base.update(overrides)
    return ReceiptInput.model_validate(base)


SOURCE = ClassificationSource(
    classifier="hand",
    model_id="hand-written",
    provider_endpoint="none",
    prompt_version="test",
    cache_key="hand",
    request_id=None,
    cost_usd=None,
    prompt_tokens=None,
    completion_tokens=None,
    cache_hit=True,
)


def cls(
    line_id: str,
    category: str,
    confidence: float = 0.95,
    subtype: str = "none",
    recipient_kind: str = "none",
    recipient_name: str | None = None,
) -> Classification:
    return Classification.model_validate(
        {
            "line_id": line_id,
            "status": "classified",
            "category": category,
            "restricted": restricted_for(category),
            "confidence": confidence,
            "subtype": subtype,
            "recipient_kind": recipient_kind,
            "recipient_name": recipient_name,
            "unclassified_reason": None,
            "source": SOURCE,
        }
    )


def unclassified(line_id: str, reason: str = "gateway_error") -> Classification:
    return Classification(
        line_id=line_id,
        status="unclassified",
        category=None,
        restricted=None,
        confidence=None,
        unclassified_reason=reason,
        source=SOURCE,
    )


def classified(r: ReceiptInput, *categories: str | Classification) -> ClassifiedReceipt:
    """Pair a receipt with one category (or a full Classification) per line, in order."""
    out = []
    for line, c in zip(r.line_items, categories, strict=True):
        out.append(c if isinstance(c, Classification) else cls(line.line_id, c))
    return ClassifiedReceipt(receipt=r, classifications=tuple(out))


def line_ids(r: ReceiptInput) -> list[str]:
    return [line.line_id for line in r.line_items]


__all__ = ["D", "LineItemInput", "classified", "cls", "item", "receipt", "unclassified"]
