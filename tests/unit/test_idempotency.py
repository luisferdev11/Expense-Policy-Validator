"""Idempotency keys and the canonical receipt form (ADR 0007 D4, FR-002, FR-009)."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from expense_validator.adapters.receipts_file import parse_receipt_line
from expense_validator.domain.idempotency import (
    MAX_KEY_LENGTH,
    canonical_receipt,
    content_hash,
    default_key,
    validate_client_key,
)
from tests.factories import item, receipt

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "receipt_with_answers.json"


def test_the_hash_ignores_how_a_decimal_was_written() -> None:
    a = receipt([item(1, amount="10.0")])
    b = receipt([item(1, amount="10.00")])
    assert content_hash(a) == content_hash(b)


def test_the_hash_changes_when_the_content_changes() -> None:
    assert content_hash(receipt([item(1, amount="10.00")])) != content_hash(
        receipt([item(1, amount="10.01")])
    )


def test_the_canonical_form_is_key_sorted_json() -> None:
    parsed = json.loads(canonical_receipt(receipt()))
    assert list(parsed) == sorted(parsed)
    assert Decimal(parsed["total_amount"]) == Decimal("10.00")


def test_the_same_receipt_with_and_without_answer_keys_hashes_the_same() -> None:
    with_answers = parse_receipt_line(FIXTURE.read_text(encoding="utf-8"))
    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    raw.pop("labels")
    raw.pop("notes")
    for line in raw["line_items"]:
        line.pop("labels")
    without = parse_receipt_line(json.dumps(raw))
    assert content_hash(with_answers) == content_hash(without)


def test_the_default_key_is_the_receipt_id_and_the_hash() -> None:
    r = receipt()
    assert default_key(r) == f"{r.receipt_id}:{content_hash(r)}"


def test_a_client_key_is_trimmed_and_bounded() -> None:
    assert validate_client_key("  abc  ") == "abc"
    with pytest.raises(ValueError, match="empty"):
        validate_client_key("   ")
    with pytest.raises(ValueError, match="at most"):
        validate_client_key("x" * (MAX_KEY_LENGTH + 1))
