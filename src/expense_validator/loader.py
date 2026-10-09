"""The only reader of data/receipts.jsonl, and the labels firewall (FR-001).

The file holds the correct answers in `labels`, `line_items[].labels` and `notes`. They are
deleted immediately after parsing, before validation, so nothing downstream can see them.
Ported from explorations/lib/receipts_safe.py. Numbers parse as Decimal (research R2).
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

from expense_validator.models import ReceiptInput
from expense_validator.paths import DATA_DIR

RECEIPTS_FILE = DATA_DIR / "receipts.jsonl"
_ANSWER_KEYS_RECEIPT = ("labels", "notes")
_ANSWER_KEYS_LINE = ("labels",)


def _strip(raw: dict[str, Any]) -> dict[str, Any]:
    for key in _ANSWER_KEYS_RECEIPT:
        raw.pop(key, None)
    for item in raw.get("line_items") or []:
        for key in _ANSWER_KEYS_LINE:
            item.pop(key, None)
    return raw


def parse_receipt_line(line: str) -> ReceiptInput:
    """Parse one JSONL line, strip the answer keys, and validate it."""
    raw = json.loads(line, parse_float=Decimal)
    return ReceiptInput.model_validate(_strip(raw))


def load_receipts(path: Path = RECEIPTS_FILE) -> list[ReceiptInput]:
    """Return every receipt with the answer keys removed, in file order."""
    with path.open(encoding="utf-8") as fh:
        return [parse_receipt_line(line) for line in fh if line.strip()]
