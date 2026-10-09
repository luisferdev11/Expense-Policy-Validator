"""Typed interfaces between components (T006, data-model.md)."""

from decimal import Decimal
from typing import Any

import pytest
from pydantic import ValidationError

from expense_validator.domain.models import (
    Classification,
    ClassificationSource,
    ExceptionFinding,
    LineItemInput,
    ReceiptInput,
)


def line(**extra: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "line_id": "SYN-1-L1",
        "description_raw": "USB-C dock",
        "language": "en",
        "quantity": Decimal("1"),
        "unit_price": Decimal("189.00"),
        "amount": Decimal("189.00"),
        "amount_usd": Decimal("189.00"),
    }
    return base | extra


def receipt(**extra: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "receipt_id": "SYN-1",
        "employee_id": "E-1",
        "employee_country": "US",
        "entity": "GLOBAL",
        "submitted_expense_type": "Computer Equipment",
        "merchant_name": "Shop",
        "mcc": 5732,
        "mcc_description": "Electronics stores",
        "transaction_datetime": "2026-05-01T10:00:00",
        "currency": "USD",
        "fx_rate_to_usd": Decimal("1"),
        "total_amount": Decimal("189.00"),
        "total_amount_usd": Decimal("189.00"),
        "attendee_count": None,
        "trip_id": None,
        "trip_nights": None,
        "pre_approval_ref": None,
        "itemized": True,
        "line_items": [line()],
    }
    return base | extra


def source() -> ClassificationSource:
    return ClassificationSource(
        classifier="fake",
        model_id="fake-model",
        provider_endpoint="none",
        prompt_version="test",
        cache_key="k",
        request_id=None,
        cost_usd=None,
        prompt_tokens=None,
        completion_tokens=None,
        cache_hit=False,
    )


def test_receipt_parses_and_money_is_decimal() -> None:
    r = ReceiptInput.model_validate(receipt())
    assert isinstance(r.total_amount_usd, Decimal)
    assert isinstance(r.line_items[0].unit_price, Decimal)
    assert r.vat_number is None


@pytest.mark.parametrize("key", ["labels", "notes", "anything_else"])
def test_receipt_rejects_unknown_keys(key: str) -> None:
    with pytest.raises(ValidationError):
        ReceiptInput.model_validate(receipt(**{key: {}}))


def test_line_item_rejects_an_answer_key() -> None:
    with pytest.raises(ValidationError):
        LineItemInput.model_validate(line(labels={}))


def test_models_are_frozen() -> None:
    r = ReceiptInput.model_validate(receipt())
    with pytest.raises(ValidationError):
        r.receipt_id = "other"  # type: ignore[misc]


def test_subtype_must_be_none_unless_category_is_other() -> None:
    with pytest.raises(ValidationError):
        Classification(
            line_id="L1",
            status="classified",
            category="food_beverage",
            restricted=False,
            confidence=0.9,
            subtype="event_ticket",
            recipient_kind="none",
            recipient_name=None,
            unclassified_reason=None,
            source=source(),
        )


def test_null_category_only_when_unclassified() -> None:
    with pytest.raises(ValidationError):
        Classification(
            line_id="L1",
            status="classified",
            category=None,
            restricted=None,
            confidence=None,
            subtype="none",
            recipient_kind="none",
            recipient_name=None,
            unclassified_reason=None,
            source=source(),
        )
    unclassified = Classification(
        line_id="L1",
        status="unclassified",
        category=None,
        restricted=None,
        confidence=None,
        subtype="none",
        recipient_kind="none",
        recipient_name=None,
        unclassified_reason="gateway_error",
        source=source(),
    )
    assert unclassified.unclassified_reason == "gateway_error"


def test_exception_severity_is_closed() -> None:
    with pytest.raises(ValidationError):
        ExceptionFinding(
            rule_id="TECH-02",
            policy_doc="technology-and-equipment-policy.md",
            severity="review",  # type: ignore[arg-type]
            line_ids=[],
            evidence="x",
            explanation="",
            decisions=[],
            computed={},
        )
