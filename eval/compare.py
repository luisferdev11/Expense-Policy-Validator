"""Compare committed results with the answers, one row per receipt (data/README.md rules).

Rows are sorted by receipt_id. Each row carries the prediction and the answer side by side, so
metrics and the viewer read one file; the viewer never reads the receipts' answer fields.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from eval.answers import Answer
from eval.scope import in_scope
from expense_validator.models import ReceiptResult


def compare(results: Sequence[ReceiptResult], answers: dict[str, Answer]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for result in sorted(results, key=lambda r: r.receipt_id):
        answer = answers[result.receipt_id]
        rows.append(
            {
                "receipt_id": result.receipt_id,
                "scored": in_scope(result.receipt_id),
                "predicted_disposition": result.disposition,
                "answer_disposition": answer.disposition,
                "lines": [
                    {
                        "line_id": line.line_id,
                        "predicted_category": line.category,
                        "predicted_restricted": line.restricted,
                        "answer_category": answer.lines[line.line_id]["category"],
                        "answer_restricted": answer.lines[line.line_id]["restricted"],
                    }
                    for line in result.line_items
                ],
                "predicted_exceptions": [
                    {
                        "rule_id": e.rule_id,
                        "severity": e.severity,
                        "line_ids": e.line_ids,
                        "computed": e.computed,
                    }
                    for e in result.exceptions
                ],
                "predicted_signals": [
                    {"rule_id": s.rule_id, "line_ids": s.line_ids} for s in result.review_signals
                ],
                "answer_exceptions": list(answer.exceptions),
                "answer_signals": list(answer.signals),
                "answer_notes": answer.notes,
            }
        )
    return rows
