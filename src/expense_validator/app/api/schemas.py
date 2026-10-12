"""Response models of the HTTP API (specs/004-backend-lifecycle/contracts/api.md).

Receipts and results are returned as the JSON the pipeline already writes. Money is a string in
JSON, so no precision is lost in transit.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict

from expense_validator.app.batching import BatchView
from expense_validator.app.reviewing import ActionResult
from expense_validator.app.service import ReceiptView, RevisionView, SubmitOutcome
from expense_validator.ports.store import EventRecord, ReceiptRecord


class SubmitResponse(BaseModel):
    receipt_id: str
    revision: int
    outcome: str
    state: str
    superseded: bool = False

    @classmethod
    def of(cls, outcome: SubmitOutcome) -> SubmitResponse:
        return cls(
            receipt_id=outcome.receipt_id,
            revision=outcome.revision,
            outcome=outcome.outcome,
            state=outcome.state,
            superseded=outcome.superseded,
        )


class FailureInfo(BaseModel):
    stage: str
    reason: str | None


class ReceiptSummary(BaseModel):
    receipt_id: str
    revision: int
    state: str
    disposition: str | None
    evaluation_version: int | None
    notice: str | None
    qa_sample: bool
    updated_at: str
    created_at: str

    @classmethod
    def of(cls, record: ReceiptRecord) -> ReceiptSummary:
        return cls(
            receipt_id=record.receipt_id,
            revision=record.current_revision,
            state=record.state,
            disposition=record.disposition,
            evaluation_version=record.evaluation_version,
            notice=record.notice,
            qa_sample=record.qa_sample,
            updated_at=record.updated_at,
            created_at=record.created_at,
        )


class ReceiptDetail(ReceiptSummary):
    failed: FailureInfo | None
    receipt: dict[str, Any]
    result: dict[str, Any] | None
    allowed_actions: list[str]

    @classmethod
    def from_view(cls, view: ReceiptView) -> ReceiptDetail:
        summary = ReceiptSummary.of(view.record)
        failed = (
            FailureInfo(stage=view.record.failed_stage, reason=view.record.failed_reason)
            if view.record.failed_stage
            else None
        )
        return cls(
            **summary.model_dump(),
            failed=failed,
            receipt=view.receipt.model_dump(mode="json"),
            result=view.result.model_dump(mode="json") if view.result else None,
            allowed_actions=list(view.allowed_actions),
        )


class ActionBody(BaseModel):
    """What a reviewer sends; unknown fields are refused."""

    model_config = ConfigDict(extra="forbid")

    actor: str
    evaluation_version: int
    note: str | None = None
    reason_code: str | None = None
    line_id: str | None = None
    category: str | None = None
    question: str | None = None
    reason: str | None = None


class ActionResponse(ReceiptDetail):
    agreement: int

    @classmethod
    def from_result(cls, result: ActionResult) -> ActionResponse:
        detail = ReceiptDetail.from_view(result.view)
        return cls(**detail.model_dump(), agreement=result.agreement)


class ReceiptList(BaseModel):
    items: list[ReceiptSummary]
    total: int


class EventItem(BaseModel):
    seq: int
    revision: int
    type: str
    actor: str
    at: str
    payload: dict[str, Any]

    @classmethod
    def of(cls, record: EventRecord) -> EventItem:
        return cls(
            seq=record.seq,
            revision=record.revision,
            type=record.event.type,
            actor=record.actor,
            at=record.at,
            payload=record.event.model_dump(mode="json", exclude={"type"}),
        )


class EventList(BaseModel):
    items: list[EventItem]


class EvaluationItem(BaseModel):
    version: int
    created_at: str
    result: dict[str, Any]


class RevisionDetail(BaseModel):
    receipt_id: str
    revision: int
    status: str
    created_at: str
    receipt: dict[str, Any]
    evaluations: list[EvaluationItem]

    @classmethod
    def of(cls, view: RevisionView) -> RevisionDetail:
        rev = view.revision
        return cls(
            receipt_id=rev.receipt_id,
            revision=rev.revision,
            status=rev.status,
            created_at=rev.created_at,
            receipt=rev.receipt.model_dump(mode="json"),
            evaluations=[
                EvaluationItem(
                    version=e.version,
                    created_at=e.created_at,
                    result=e.result.model_dump(mode="json"),
                )
                for e in view.evaluations
            ],
        )


class BatchItem(BaseModel):
    row: int
    receipt_id: str | None
    outcome: str
    error: str | None
    state: str | None


class BatchResponse(BaseModel):
    batch_id: str
    total: int
    created_at: str
    counts: dict[str, int]
    items: list[BatchItem]

    @classmethod
    def of(cls, view: BatchView) -> BatchResponse:
        return cls(
            batch_id=view.batch_id,
            total=view.total,
            created_at=view.created_at,
            counts=view.counts,
            items=[
                BatchItem(
                    row=i.row,
                    receipt_id=i.receipt_id,
                    outcome=i.outcome,
                    error=i.error,
                    state=i.state,
                )
                for i in view.items
            ],
        )


class Health(BaseModel):
    status: str
    schema_version: int
