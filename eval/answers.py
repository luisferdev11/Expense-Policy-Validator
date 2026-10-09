"""The only reader of the answer fields in data/receipts.jsonl (constitution I).

Answers are used to score committed outputs. They never flow back into the pipeline.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from expense_validator.paths import DATA_DIR

ANSWERS_FILE = DATA_DIR / "receipts.jsonl"


@dataclass(frozen=True)
class Answer:
    receipt_id: str
    disposition: str
    exceptions: tuple[dict[str, Any], ...]
    signals: tuple[dict[str, Any], ...]
    lines: dict[str, dict[str, Any]]
    notes: str = field(default="")


def load_answers(path: Path = ANSWERS_FILE) -> dict[str, Answer]:
    answers: dict[str, Answer] = {}
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            raw = json.loads(line)
            labels = raw["labels"]
            answers[raw["receipt_id"]] = Answer(
                receipt_id=raw["receipt_id"],
                disposition=labels["disposition"],
                exceptions=tuple(labels.get("expected_exceptions") or ()),
                signals=tuple(labels.get("review_signals") or ()),
                lines={
                    item["line_id"]: {
                        "category": item["labels"]["category"],
                        "restricted": item["labels"]["restricted"],
                    }
                    for item in raw["line_items"]
                },
                notes=raw.get("notes") or "",
            )
    return answers
