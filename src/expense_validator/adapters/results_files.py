"""Output files: write results canonically, and read committed outputs (ADR 0002, ADR 0003).

The viewer reads results, the evaluation's comparison and its metrics only through here: the
seam for a future API.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from expense_validator.domain.models import ReceiptResult
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


def load_experiments(path: Path = EVAL_DIR / "experiments.json") -> dict[str, Any]:
    """The iteration 2 decisions written by eval/experiments/decide.py, or {} before they exist."""
    return load_metrics(path)


def write_results(path: Path, results: Sequence[ReceiptResult]) -> None:
    """Canonical JSONL: model field order, one receipt per line, sorted by the caller."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(r.model_dump(mode="json"), ensure_ascii=False) for r in results]
    path.write_text("".join(line + "\n" for line in lines), encoding="utf-8")
