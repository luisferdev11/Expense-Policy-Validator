"""The loader is the labels firewall (T008, FR-001, FR-002).

These tests never print or assert any answer value: they check only that answer keys are gone.
"""

import json
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from expense_validator.adapters.receipts_file import load_receipts, parse_receipt_line


def test_loads_32_receipts_and_79_items() -> None:
    receipts = load_receipts()
    assert len(receipts) == 32
    assert sum(len(r.line_items) for r in receipts) == 79


def test_no_answer_key_survives() -> None:
    for r in load_receipts():
        dumped = r.model_dump()
        assert "labels" not in dumped
        assert "notes" not in dumped
        for item in dumped["line_items"]:
            assert "labels" not in item


def test_amounts_are_decimal() -> None:
    r = load_receipts()[0]
    assert isinstance(r.fx_rate_to_usd, Decimal | None)
    assert isinstance(r.line_items[0].amount_usd, Decimal)


def test_answer_keys_are_stripped_from_a_raw_line() -> None:
    raw = (Path(__file__).parent.parent / "fixtures" / "receipt_with_answers.json").read_text()
    receipt = parse_receipt_line(raw)
    assert receipt.receipt_id == "SYN-FIREWALL"


def test_an_unexpected_extra_key_fails_validation() -> None:
    raw = json.loads(
        (Path(__file__).parent.parent / "fixtures" / "receipt_with_answers.json").read_text()
    )
    raw["expected_disposition"] = "flag"
    with pytest.raises(ValidationError):
        parse_receipt_line(json.dumps(raw))
