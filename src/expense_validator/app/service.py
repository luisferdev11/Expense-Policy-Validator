"""Use cases of the backend: submit, read (ADR 0006, ADR 0007).

Every command is one transaction on the store: the event, the projection and the outbox row
commit together, so a receipt is never stored without its work being queued, and a response is
never sent before the receipt is durable. The only way in is `parse_receipt_line`, which strips
the answer keys (rule 1); the stripped receipt is what is hashed, stored and returned.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import ValidationError

from expense_validator.adapters.receipts_file import parse_receipt_line
from expense_validator.app.errors import (
    ActionNotAllowedError,
    IdempotencyKeyReuseError,
    InvalidIdempotencyKeyError,
    InvalidReceiptError,
    NotFoundError,
)
from expense_validator.domain.cascade import sharing_keys
from expense_validator.domain.events import ReceiptSubmitted, RevisionSuperseded, StageRetried
from expense_validator.domain.idempotency import content_hash, default_key, validate_client_key
from expense_validator.domain.lifecycle import Action, allowed_actions, decision_after
from expense_validator.domain.models import ReceiptInput, ReceiptResult
from expense_validator.ports.store import (
    Clock,
    EvaluationRecord,
    EventRecord,
    ListOrder,
    ReceiptRecord,
    ReceiptStore,
    RevisionRecord,
    StoreTx,
    SubmissionRecord,
    stamp,
)

SYSTEM = "system"
Outcome = Literal["accepted", "existing", "revision"]


@dataclass(frozen=True)
class SubmitOutcome:
    receipt_id: str
    revision: int
    outcome: Outcome
    state: str
    superseded: bool = False


@dataclass(frozen=True)
class ReceiptView:
    """A receipt's current revision with its latest evaluation and what a reviewer may do."""

    record: ReceiptRecord
    receipt: ReceiptInput
    result: ReceiptResult | None
    allowed_actions: tuple[Action, ...]


@dataclass(frozen=True)
class RevisionView:
    revision: RevisionRecord
    evaluations: tuple[EvaluationRecord, ...]


def parse_receipt(raw: str | bytes) -> ReceiptInput:
    """Parse one receipt from JSON text. Answer keys are stripped; numbers stay exact."""
    text = raw.decode("utf-8") if isinstance(raw, bytes) else raw
    try:
        value = json.loads(text, parse_float=Decimal)
    except json.JSONDecodeError as exc:
        raise InvalidReceiptError(f"not valid JSON: {exc.msg}") from exc
    if not isinstance(value, dict):
        raise InvalidReceiptError("a receipt is a JSON object")
    try:
        return parse_receipt_line(text)
    except ValidationError as exc:
        fields = sorted({".".join(str(p) for p in e["loc"]) for e in exc.errors()})
        raise InvalidReceiptError(
            f"not a valid receipt: {', '.join(fields[:5])}", {"fields": fields}
        ) from exc


class ReceiptService:
    def __init__(self, store: ReceiptStore, clock: Clock) -> None:
        self.store = store
        self.clock = clock

    def submit(
        self, raw: str | bytes, client_key: str | None = None, batch_id: str | None = None
    ) -> SubmitOutcome:
        receipt = parse_receipt(raw)
        return self.submit_parsed(receipt, client_key, batch_id)

    def submit_parsed(
        self, receipt: ReceiptInput, client_key: str | None = None, batch_id: str | None = None
    ) -> SubmitOutcome:
        digest = content_hash(receipt)
        try:
            key = validate_client_key(client_key) if client_key is not None else None
        except ValueError as exc:
            raise InvalidIdempotencyKeyError(str(exc)) from exc
        used_key = key or default_key(receipt)
        now = self.clock()
        with self.store.transaction() as tx:
            existing = self._existing(tx, receipt, used_key, digest, key is not None, now)
            if existing is not None:
                return existing
            return self._store_revision(tx, receipt, used_key, digest, batch_id, now)

    def retry(self, receipt_id: str) -> ReceiptRecord:
        """Queue a failed receipt again at the stage that failed (FR-015)."""
        now = self.clock()
        with self.store.transaction() as tx:
            record = tx.get_receipt(receipt_id)
            if record is None:
                raise NotFoundError(f"no receipt {receipt_id!r}")
            if record.failed_stage is None:
                raise ActionNotAllowedError(
                    f"the receipt is {record.state!r} and has no failure to retry"
                )
            stage = record.failed_stage
            tx.enqueue(receipt_id, record.current_revision, stage, now)
            # A receipt that never got an evaluation is `failed` and goes back into the
            # pipeline; one that already has a state (a re-evaluation failed) keeps it.
            state = record.state
            decided_by, decided_at = record.decided_by, record.decided_at
            if state == "failed":
                state = "submitted" if stage == "classify" else "classifying"
                decided_by, decided_at = decision_after(
                    state, actor=SYSTEM, at=stamp(now), by_human_action=False
                )
            updated = replace(
                record,
                state=state,
                failed_stage=None,
                failed_reason=None,
                updated_at=stamp(now),
                decided_by=decided_by,
                decided_at=decided_at,
            )
            tx.put_receipt(updated)
            tx.append_event(
                receipt_id, record.current_revision, StageRetried(stage=stage), SYSTEM, now
            )
        return updated

    # Reads

    def get_receipt(self, receipt_id: str) -> ReceiptView:
        with self.store.transaction(write=False) as tx:
            record = tx.get_receipt(receipt_id)
            if record is None:
                raise NotFoundError(f"no receipt {receipt_id!r}")
            revision = tx.get_revision(receipt_id, record.current_revision)
            assert revision is not None
            evaluation = tx.latest_evaluation(receipt_id, record.current_revision)
        return ReceiptView(
            record=record,
            receipt=revision.receipt,
            result=evaluation.result if evaluation else None,
            allowed_actions=allowed_actions(record.state),
        )

    def list_receipts(
        self,
        *,
        state: str | None = None,
        disposition: str | None = None,
        batch_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
        order: ListOrder = "receipt_id",
    ) -> tuple[list[ReceiptRecord], int]:
        with self.store.transaction(write=False) as tx:
            return tx.list_receipts(
                state=state,
                disposition=disposition,
                batch_id=batch_id,
                limit=limit,
                offset=offset,
                order=order,
            )

    def list_events(self, receipt_id: str) -> list[EventRecord]:
        with self.store.transaction(write=False) as tx:
            if tx.get_receipt(receipt_id) is None:
                raise NotFoundError(f"no receipt {receipt_id!r}")
            return tx.list_events(receipt_id)

    def get_revision(self, receipt_id: str, revision: int) -> RevisionView:
        with self.store.transaction(write=False) as tx:
            found = tx.get_revision(receipt_id, revision)
            if found is None:
                raise NotFoundError(f"no revision {revision} of receipt {receipt_id!r}")
            evaluations = tx.list_evaluations(receipt_id, revision)
        return RevisionView(found, tuple(evaluations))

    def _existing(
        self,
        tx: StoreTx,
        receipt: ReceiptInput,
        key: str,
        digest: str,
        explicit: bool,
        now: datetime,
    ) -> SubmitOutcome | None:
        """The outcome when this submission is a repeat, otherwise None."""
        current = tx.get_receipt(receipt.receipt_id)
        sub = tx.get_submission(key)
        if sub is not None:
            if sub.content_hash != digest:
                raise IdempotencyKeyReuseError(
                    "this idempotency key was used with a different body",
                    {"idempotency_key": key},
                )
            assert current is not None
            # A default key that points at an old revision is a return to earlier content.
            if explicit or sub.revision == current.current_revision:
                return SubmitOutcome(
                    current.receipt_id,
                    current.current_revision,
                    "existing",
                    current.state,
                    superseded=sub.revision != current.current_revision,
                )
            return None
        if current is None:
            return None
        latest = tx.get_revision(current.receipt_id, current.current_revision)
        assert latest is not None
        if latest.content_hash != digest:
            return None
        tx.put_submission(
            SubmissionRecord(key, current.receipt_id, current.current_revision, digest, None), now
        )
        return SubmitOutcome(
            current.receipt_id, current.current_revision, "existing", current.state
        )

    def _store_revision(
        self,
        tx: StoreTx,
        receipt: ReceiptInput,
        key: str,
        digest: str,
        batch_id: str | None,
        now: datetime,
    ) -> SubmitOutcome:
        rid = receipt.receipt_id
        current = tx.get_receipt(rid)
        revision = 1 if current is None else current.current_revision + 1
        if current is not None:
            tx.cancel_open_work(rid, current.current_revision)
            tx.mark_superseded(rid, current.current_revision)
            tx.append_event(
                rid,
                revision,
                RevisionSuperseded(
                    superseded_revision=current.current_revision, by_revision=revision
                ),
                SYSTEM,
                now,
            )
        tx.add_revision(rid, revision, digest, receipt, sharing_keys(receipt), now)
        tx.put_submission(SubmissionRecord(key, rid, revision, digest, batch_id), now)
        tx.append_event(
            rid,
            revision,
            ReceiptSubmitted(content_hash=digest, idempotency_key=key, batch_id=batch_id),
            SYSTEM,
            now,
        )
        decided_by, decided_at = decision_after(
            "submitted", actor=SYSTEM, at=stamp(now), by_human_action=False
        )
        tx.put_receipt(
            ReceiptRecord(
                receipt_id=rid,
                current_revision=revision,
                state="submitted",
                disposition=None,
                evaluation_version=None,
                human_acted=False,
                notice=None,
                qa_sample=False,
                failed_stage=None,
                failed_reason=None,
                updated_at=stamp(now),
                created_at=stamp(now) if current is None else current.created_at,
                decided_by=decided_by,
                decided_at=decided_at,
            )
        )
        tx.enqueue(rid, revision, "classify", now)
        return SubmitOutcome(
            rid, revision, "accepted" if revision == 1 else "revision", "submitted"
        )
