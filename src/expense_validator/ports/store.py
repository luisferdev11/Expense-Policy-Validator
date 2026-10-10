"""The receipt store port (ADR 0007 D1): events, projections and the outbox, in transactions.

One transaction per command: the event, the projection update and the outbox row commit
together or not at all. The only implementation today is SQLite (`adapters/sqlite_store.py`);
the port is the seam to DynamoDB and SQS on AWS, not a speculative abstraction.
"""

from __future__ import annotations

from collections.abc import Callable, Collection, Sequence
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from expense_validator.domain.events import Event
from expense_validator.domain.lifecycle import Stage, State
from expense_validator.domain.models import (
    Classification,
    Disposition,
    ReceiptInput,
    ReceiptResult,
)

Clock = Callable[[], datetime]


@dataclass(frozen=True)
class ReceiptRecord:
    """The projection of a receipt's current revision."""

    receipt_id: str
    current_revision: int
    state: State
    disposition: Disposition | None
    evaluation_version: int | None
    human_acted: bool
    notice: str | None
    qa_sample: bool
    failed_stage: Stage | None
    failed_reason: str | None
    updated_at: str


@dataclass(frozen=True)
class SubmissionRecord:
    idempotency_key: str
    receipt_id: str
    revision: int
    content_hash: str
    batch_id: str | None


@dataclass(frozen=True)
class RevisionRecord:
    receipt_id: str
    revision: int
    content_hash: str
    receipt: ReceiptInput
    status: str
    created_at: str


@dataclass(frozen=True)
class EvaluationRecord:
    receipt_id: str
    revision: int
    version: int
    result: ReceiptResult
    result_hash: str
    created_at: str


@dataclass(frozen=True)
class EventRecord:
    seq: int
    receipt_id: str
    revision: int
    event: Event
    actor: str
    at: str


@dataclass(frozen=True)
class WorkItem:
    id: int
    receipt_id: str
    revision: int
    stage: Stage
    attempts: int


@dataclass(frozen=True)
class BatchItemRecord:
    row: int
    receipt_id: str | None
    outcome: str
    error: str | None


@dataclass(frozen=True)
class BatchRecord:
    batch_id: str
    total: int
    created_at: str
    items: tuple[BatchItemRecord, ...]


class StoreTx(Protocol):
    """Operations available inside one transaction. Writes need `transaction(write=True)`."""

    # Idempotency
    def get_submission(self, key: str) -> SubmissionRecord | None: ...
    def put_submission(self, record: SubmissionRecord, now: datetime) -> None: ...

    # Receipts (projection)
    def get_receipt(self, receipt_id: str) -> ReceiptRecord | None: ...
    def put_receipt(self, record: ReceiptRecord) -> None: ...
    def list_receipts(
        self,
        *,
        state: str | None = None,
        disposition: str | None = None,
        batch_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[ReceiptRecord], int]: ...

    # Revisions
    def add_revision(
        self,
        receipt_id: str,
        revision: int,
        content_hash: str,
        receipt: ReceiptInput,
        keys: Collection[str],
        now: datetime,
    ) -> None: ...
    def get_revision(self, receipt_id: str, revision: int) -> RevisionRecord | None: ...
    def list_revisions(self, receipt_id: str) -> list[RevisionRecord]: ...
    def mark_superseded(self, receipt_id: str, revision: int) -> None: ...
    def keys_of_receipt(self, receipt_id: str) -> frozenset[str]: ...
    def current_receipts_sharing(self, keys: Collection[str]) -> list[str]: ...

    # Classifications of a revision (the model's answers; human corrections are events)
    def save_classifications(
        self, receipt_id: str, revision: int, classifications: Sequence[Classification]
    ) -> None: ...
    def load_classifications(
        self, receipt_id: str, revision: int
    ) -> tuple[Classification, ...] | None: ...

    # Evaluations (versioned)
    def add_evaluation(
        self,
        receipt_id: str,
        revision: int,
        result: ReceiptResult,
        result_hash: str,
        now: datetime,
    ) -> int: ...
    def latest_evaluation(self, receipt_id: str, revision: int) -> EvaluationRecord | None: ...
    def list_evaluations(self, receipt_id: str, revision: int) -> list[EvaluationRecord]: ...

    # Events (append-only)
    def append_event(
        self, receipt_id: str, revision: int, event: Event, actor: str, now: datetime
    ) -> int: ...
    def list_events(self, receipt_id: str) -> list[EventRecord]: ...

    # Outbox
    def enqueue(self, receipt_id: str, revision: int, stage: Stage, now: datetime) -> bool: ...
    def cancel_open_work(self, receipt_id: str, revision: int) -> int: ...
    def claim_work(self, now: datetime, lease_until: datetime) -> WorkItem | None: ...
    def complete_work(self, item_id: int) -> None: ...
    def fail_work(self, item_id: int, error: str) -> None: ...
    def open_work_count(self) -> int: ...

    # Batches
    def add_batch(self, batch_id: str, items: Sequence[BatchItemRecord], now: datetime) -> None: ...
    def get_batch(self, batch_id: str) -> BatchRecord | None: ...
    def batch_state_counts(self, batch_id: str) -> dict[str, int]: ...


class ReceiptStore(Protocol):
    @property
    def schema_version(self) -> int: ...

    def transaction(self, *, write: bool = True) -> AbstractContextManager[StoreTx]: ...
