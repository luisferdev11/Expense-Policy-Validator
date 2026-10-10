"""Comparing evaluations (ADR 0007 D7, research R5).

A re-evaluation is recorded as a new version only when its result changed. The comparison is a
hash of what a reviewer sees: the disposition, the exceptions, the review signals and how each
line was classified. The run metadata is left out, so the same decision made by another model
build is not a "change" of the decision itself.
"""

from __future__ import annotations

import hashlib
import json

from expense_validator.domain.models import ReceiptResult


def result_hash(result: ReceiptResult) -> str:
    payload = {
        "disposition": result.disposition,
        "exceptions": [e.model_dump(mode="json") for e in result.exceptions],
        "review_signals": [s.model_dump(mode="json") for s in result.review_signals],
        "line_items": [i.model_dump(mode="json") for i in result.line_items],
    }
    text = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
