"""Label-stripping loader for data/receipts.jsonl.

The file holds the correct answers in `labels`, `line_items[].labels` and `notes`. This loader
deletes those keys immediately after json.loads, so nothing downstream can see them. It is the
only way anything in explorations/ reads the receipts.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ANSWER_KEYS_RECEIPT = ("labels", "notes")
ANSWER_KEYS_LINE = ("labels",)


def repo_root() -> Path:
    here = Path(__file__).resolve().parent
    return here.parent


def _strip(receipt: dict[str, Any]) -> dict[str, Any]:
    for key in ANSWER_KEYS_RECEIPT:
        receipt.pop(key, None)
    for item in receipt.get("line_items") or []:
        for key in ANSWER_KEYS_LINE:
            item.pop(key, None)
    return receipt


def load_inputs(path: Path | None = None) -> list[dict[str, Any]]:
    """Return every receipt with the answer keys removed."""
    path = path or repo_root() / "data" / "receipts.jsonl"
    out = []
    with path.open() as fh:
        for line in fh:
            if line.strip():
                out.append(_strip(json.loads(line)))
    return out


def assert_clean(receipts: list[dict[str, Any]]) -> None:
    """Fail loudly if any answer key survived."""
    for r in receipts:
        assert not any(k in r for k in ANSWER_KEYS_RECEIPT)
        for item in r.get("line_items") or []:
            assert not any(k in item for k in ANSWER_KEYS_LINE)
