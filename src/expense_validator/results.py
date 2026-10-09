"""Read-only access to committed outputs: the seam for the viewer and a future API (ADR 0002).

The viewer reads results, the evaluation's comparison and its metrics only through here.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from expense_validator.models import ReceiptResult
from expense_validator.paths import EVAL_DIR, RESULTS_FILE


def load_results(path: Path = RESULTS_FILE) -> list[ReceiptResult]:
    if not path.exists():
        return []
    return [
        ReceiptResult.model_validate_json(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def load_comparison(path: Path = EVAL_DIR / "comparison.jsonl") -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def load_metrics(path: Path = EVAL_DIR / "metrics.json") -> dict[str, Any]:
    if not path.exists():
        return {}
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return data
