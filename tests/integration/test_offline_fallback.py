"""With no cache and no model, no itemized receipt passes (T075, FR-009, SC-006).

A non-itemized charge is `other` by definition (EXC-03), so its receipt does not depend on the
classifier at all; every itemized receipt depends on it and must go to review or flag.
"""

import json
import warnings
from pathlib import Path

from expense_validator.cli import run_command
from expense_validator.loader import load_receipts


def test_empty_cache_offline_never_passes_an_itemized_receipt(tmp_path: Path) -> None:
    results = tmp_path / "r.jsonl"
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        run_command(
            offline=True, no_trace=True, results_path=results, cache_path=tmp_path / "empty.jsonl"
        )
    itemized = {r.receipt_id: r.itemized for r in load_receipts()}
    rows = [json.loads(line) for line in results.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 32
    for row in rows:
        assert all(
            (line["status"], line["unclassified_reason"]) == ("unclassified", "offline_cache_miss")
            for line in row["line_items"]
        )
        if itemized[row["receipt_id"]]:
            assert "EXC-03" in {s["rule_id"] for s in row["review_signals"]}, row["receipt_id"]
            assert row["disposition"] != "pass", row["receipt_id"]
