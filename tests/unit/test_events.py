"""Typed events of the append-only log (data-model.md)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from expense_validator.domain.events import (
    EVENT_TYPES,
    ReceiptApproved,
    ReceiptEvaluated,
    ReceiptSubmitted,
    event_payload,
    parse_event,
)


def test_an_event_round_trips_through_its_payload() -> None:
    event = ReceiptEvaluated(version=2, disposition="flag", changed=True, result_hash="abc")
    again = parse_event(event.type, event_payload(event))
    assert again == event


def test_the_payload_does_not_repeat_the_type() -> None:
    event = ReceiptSubmitted(content_hash="h", idempotency_key="k", batch_id=None)
    assert "type" not in event_payload(event)


def test_every_declared_type_can_be_parsed_back() -> None:
    assert len(EVENT_TYPES) == 13
    assert set(EVENT_TYPES) == {cls.model_fields["type"].default for cls in EVENT_TYPES.values()}


def test_an_unknown_type_is_rejected() -> None:
    with pytest.raises(KeyError):
        parse_event("ReceiptTeleported", "{}")


def test_extra_keys_are_rejected() -> None:
    with pytest.raises(ValidationError):
        ReceiptApproved.model_validate(
            {
                "based_on_version": 1,
                "reason_code": None,
                "note": None,
                "agreement": 1,
                "labels": {"disposition": "pass"},
            }
        )
