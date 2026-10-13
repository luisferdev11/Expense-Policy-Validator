"""Synthetic receipts for the load test, from `docs/samples/receipt-one.json` (research R14).

Ids are `LT-<run>-<n>`; employees are `TEST-LT-<run>-<n % 50>`, so the load test keeps working
once roles land (spec 009, ADR 0010 D6). Every fifth receipt has no transaction date, which the
engine sends to a person, so the approve task has something to approve. Nothing here opens
`data/receipts.jsonl`.
"""

from __future__ import annotations

import copy
import json
from functools import lru_cache
from pathlib import Path
from typing import Any

SAMPLE = Path(__file__).resolve().parents[1] / "docs" / "samples" / "receipt-one.json"


@lru_cache(maxsize=1)
def _sample() -> dict[str, Any]:
    loaded: dict[str, Any] = json.loads(SAMPLE.read_text(encoding="utf-8"))
    return loaded


def is_flagged(n: int) -> bool:
    """Whether receipt number `n` is built to wait for a person."""
    return n % 5 == 0


def make_receipt(run_id: str, n: int) -> dict[str, Any]:
    body = copy.deepcopy(_sample())
    receipt_id = f"LT-{run_id}-{n:06d}"
    body["receipt_id"] = receipt_id
    body["employee_id"] = f"TEST-LT-{run_id}-{n % 50:02d}"
    for index, line in enumerate(body["line_items"], start=1):
        line["line_id"] = f"{receipt_id}-L{index}"
    if is_flagged(n):
        body["transaction_datetime"] = None
    return body


def make_batch(run_id: str, start: int, rows: int) -> str:
    """JSON Lines for receipts `start` to `start + rows - 1`."""
    return "\n".join(json.dumps(make_receipt(run_id, n)) for n in range(start, start + rows)) + "\n"
