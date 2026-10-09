"""Evaluation metrics. Every metric is reported with its N (constitution VI)."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

DISPOSITIONS = ["flag", "review", "pass"]


def confusion_matrix(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """3x3 disposition matrix over scored rows: rows are answers, columns are predictions."""
    scored = [r for r in rows if r["scored"]]
    matrix = [[0, 0, 0] for _ in DISPOSITIONS]
    for row in scored:
        i = DISPOSITIONS.index(row["answer_disposition"])
        j = DISPOSITIONS.index(row["predicted_disposition"])
        matrix[i][j] += 1
    return {"labels": list(DISPOSITIONS), "matrix": matrix, "n": len(scored)}
