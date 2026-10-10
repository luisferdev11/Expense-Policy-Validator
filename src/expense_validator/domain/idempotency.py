"""Idempotency keys and the canonical form of a receipt (ADR 0007 D4, research R6).

The hash is computed on the stripped `ReceiptInput`, so the same receipt with or without answer
keys gets the same key (FR-009). Decimals are normalised, so `10.0` and `10.00` are one number.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from decimal import Decimal
from typing import Any

from expense_validator.domain.models import ReceiptInput

MAX_KEY_LENGTH = 255


def _plain(value: Any) -> Any:
    if isinstance(value, Decimal):
        return format(value.normalize(), "f")
    if isinstance(value, datetime):
        return value.isoformat()
    raise TypeError(f"not serialisable: {type(value).__name__}")


def canonical_receipt(receipt: ReceiptInput) -> str:
    """Key-sorted, compact JSON of the receipt with normalised Decimals."""
    return json.dumps(receipt.model_dump(), sort_keys=True, separators=(",", ":"), default=_plain)


def content_hash(receipt: ReceiptInput) -> str:
    return hashlib.sha256(canonical_receipt(receipt).encode("utf-8")).hexdigest()


def default_key(receipt: ReceiptInput) -> str:
    """The key used when the client sends none: the receipt identity plus its content."""
    return f"{receipt.receipt_id}:{content_hash(receipt)}"


def validate_client_key(key: str) -> str:
    cleaned = key.strip()
    if not cleaned:
        raise ValueError("an idempotency key cannot be empty")
    if len(cleaned) > MAX_KEY_LENGTH:
        raise ValueError(f"an idempotency key has at most {MAX_KEY_LENGTH} characters")
    return cleaned
