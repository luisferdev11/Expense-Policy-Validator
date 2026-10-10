"""Typed events of the append-only log (ADR 0006 decision 1, data-model.md).

The event store is the source of truth; projections are rebuilt from it. A payload carries only
what is specific to the event: the receipt id, revision, actor and time are columns of the log.
Every model forbids extra keys, a second labels firewall.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

from expense_validator.domain.models import Disposition


class _Event(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class ReceiptSubmitted(_Event):
    type: Literal["ReceiptSubmitted"] = "ReceiptSubmitted"
    content_hash: str
    idempotency_key: str
    batch_id: str | None = None


class RevisionSuperseded(_Event):
    type: Literal["RevisionSuperseded"] = "RevisionSuperseded"
    superseded_revision: int
    by_revision: int


class ReceiptClassified(_Event):
    type: Literal["ReceiptClassified"] = "ReceiptClassified"
    lines: int
    cache_hits: int
    calls_made: int


class ReceiptEvaluated(_Event):
    type: Literal["ReceiptEvaluated"] = "ReceiptEvaluated"
    version: int
    disposition: Disposition
    changed: bool
    result_hash: str


class NoticeRaised(_Event):
    type: Literal["NoticeRaised"] = "NoticeRaised"
    text: str


class StageFailed(_Event):
    type: Literal["StageFailed"] = "StageFailed"
    stage: Literal["classify", "evaluate"]
    reason: str


class StageRetried(_Event):
    type: Literal["StageRetried"] = "StageRetried"
    stage: Literal["classify", "evaluate"]


class ReceiptApproved(_Event):
    type: Literal["ReceiptApproved"] = "ReceiptApproved"
    based_on_version: int
    reason_code: str | None
    note: str | None
    agreement: int


class ReceiptRejected(_Event):
    type: Literal["ReceiptRejected"] = "ReceiptRejected"
    based_on_version: int
    reason_code: str | None
    note: str | None
    agreement: int


class LineCategoryCorrected(_Event):
    type: Literal["LineCategoryCorrected"] = "LineCategoryCorrected"
    line_id: str
    from_category: str | None
    to_category: str
    based_on_version: int
    agreement: int


class InformationRequested(_Event):
    type: Literal["InformationRequested"] = "InformationRequested"
    question: str
    based_on_version: int
    agreement: int


class EscalatedToCompliance(_Event):
    type: Literal["EscalatedToCompliance"] = "EscalatedToCompliance"
    reason: str
    based_on_version: int
    agreement: int


class DevCandidateMarked(_Event):
    type: Literal["DevCandidateMarked"] = "DevCandidateMarked"
    line_id: str
    from_category: str | None
    to_category: str


Event = (
    ReceiptSubmitted
    | RevisionSuperseded
    | ReceiptClassified
    | ReceiptEvaluated
    | NoticeRaised
    | StageFailed
    | StageRetried
    | ReceiptApproved
    | ReceiptRejected
    | LineCategoryCorrected
    | InformationRequested
    | EscalatedToCompliance
    | DevCandidateMarked
)

EVENT_TYPES: dict[str, type[_Event]] = {
    cls.model_fields["type"].default: cls
    for cls in (
        ReceiptSubmitted,
        RevisionSuperseded,
        ReceiptClassified,
        ReceiptEvaluated,
        NoticeRaised,
        StageFailed,
        StageRetried,
        ReceiptApproved,
        ReceiptRejected,
        LineCategoryCorrected,
        InformationRequested,
        EscalatedToCompliance,
        DevCandidateMarked,
    )
}


def event_payload(event: Event) -> str:
    """The JSON stored in the log, without the type (it has its own column)."""
    return event.model_dump_json(exclude={"type"})


def parse_event(type_: str, payload: str) -> Event:
    cls = EVENT_TYPES[type_]
    parsed = cls.model_validate_json(payload)
    assert isinstance(parsed, _Event)
    return parsed  # type: ignore[return-value]
