"""Review rules of the lifecycle (ADR 0007 D8 to D10, D12).

Pure functions: when a reviewer must give a reason, whether a reviewer's action agreed with the
engine's proposal, how a human's category becomes an ordinary classification, and which
receipts go to quality review. The engine is untouched: a human category is a `Classification`
with a different source, so the engine reads it like any other.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from typing import Literal, get_args

from expense_validator.domain.lifecycle import Action
from expense_validator.domain.models import (
    Classification,
    ClassificationSource,
    Disposition,
)
from expense_validator.domain.taxonomy import CATEGORIES, Category, restricted_for

QA_SAMPLE_ONE_IN = 10

ReasonCode = Literal[
    "policy_exception_granted",
    "engine_false_positive",
    "engine_missed_issue",
    "documentation_provided",
    "other",
]
REASON_CODES: tuple[ReasonCode, ...] = get_args(ReasonCode)

AUDITOR = "auditor"


def qa_sampled(receipt_id: str, revision: int) -> bool:
    """Whether an auto-approved receipt goes to quality review: about one in ten, chosen by a
    hash of the receipt and revision, so it is reproducible and needs no randomness."""
    digest = hashlib.sha256(f"{receipt_id}:{revision}".encode()).hexdigest()
    return int(digest, 16) % QA_SAMPLE_ONE_IN == 0


def requires_reason(action: Action, proposal: Disposition) -> bool:
    """A decision that overrides the engine's proposal needs a reason code (D8)."""
    return (action == "approve" and proposal == "flag") or (
        action == "reject" and proposal == "pass"
    )


def agreement(action: Action, proposal: Disposition) -> int:
    """1 when the reviewer's action fits the engine's proposal, else 0 (D10)."""
    if action == "correct-category":
        return 0  # the reviewer disagreed with the classifier
    if action == "approve":
        return int(proposal != "flag")
    if action == "reject":
        return int(proposal != "pass")
    return int(proposal != "pass")  # request-info and escalate ask for more attention


def human_classification(
    model: Classification, category: str, receipt_id: str, revision: int, ordinal: int
) -> Classification:
    """The classification a reviewer's category stands for (D9).

    `ordinal` makes the cache key unique per correction (the event's sequence number).
    """
    if category not in CATEGORIES:
        raise ValueError(f"{category!r} is not a taxonomy category")
    chosen: Category = category  # type: ignore[assignment]
    return Classification(
        line_id=model.line_id,
        status="classified",
        category=chosen,
        restricted=restricted_for(chosen),
        confidence=1.0,
        subtype=model.subtype if chosen == "other" else "none",
        recipient_kind=model.recipient_kind,
        recipient_name=model.recipient_name,
        unclassified_reason=None,
        source=ClassificationSource(
            classifier=AUDITOR,
            model_id="human",
            provider_endpoint="none",
            prompt_version="n/a",
            cache_key=f"{AUDITOR}:{receipt_id}:{revision}:{model.line_id}:{ordinal}",
            request_id=None,
            cost_usd=None,
            prompt_tokens=None,
            completion_tokens=None,
            cache_hit=False,
        ),
    )


def apply_corrections(
    classifications: Sequence[Classification],
    receipt_id: str,
    revision: int,
    corrections: Sequence[tuple[int, str, str]],
) -> tuple[Classification, ...]:
    """Overlay the reviewers' corrections, `(sequence, line_id, category)` each, on the model's
    answers. The latest correction of a line wins; lines with none are returned as they are."""
    latest: dict[str, tuple[int, str]] = {}
    for seq, line_id, category in sorted(corrections):
        latest[line_id] = (seq, category)
    return tuple(
        human_classification(c, latest[c.line_id][1], receipt_id, revision, latest[c.line_id][0])
        if c.line_id in latest
        else c
        for c in classifications
    )
