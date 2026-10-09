"""Scoring scope (brief): the four timing receipts are processed and shown but never scored.

This list lives in eval/, never in pipeline code, which must not reference receipt IDs.
"""

from __future__ import annotations

OUT_OF_SCOPE: frozenset[str] = frozenset({"RCP-020", "RCP-021", "RCP-029", "RCP-030"})


def in_scope(receipt_id: str) -> bool:
    return receipt_id not in OUT_OF_SCOPE
