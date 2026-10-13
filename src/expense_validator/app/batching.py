"""Batches of receipts: partial success and a summary by state (FR-007, FR-008, ADR 0006).

A batch is a parent with one child per row. Each valid row is submitted on its own, with the
same rules as a single receipt (idempotent, a changed receipt is a revision), so a failure or a
bad row never affects the others, and submitting the same batch again starts no new work.
Resubmission is therefore idempotent per receipt; the batch itself is a new record each time.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from expense_validator.app.errors import (
    AppError,
    InvalidBatchError,
    InvalidReceiptError,
    NotFoundError,
)
from expense_validator.app.intake import split_rows
from expense_validator.app.service import ReceiptService, parse_receipt
from expense_validator.ports.store import BatchItemRecord

MAX_ROWS = 1000
PROBLEM_OUTCOMES = frozenset({"invalid", "duplicate_in_batch"})


@dataclass(frozen=True)
class BatchItemView:
    row: int
    receipt_id: str | None
    outcome: str
    error: str | None
    state: str | None  # the receipt's current state; None for a row that was not accepted


@dataclass(frozen=True)
class BatchView:
    batch_id: str
    total: int
    created_at: str
    counts: dict[str, int]
    items: tuple[BatchItemView, ...]

    @property
    def has_problems(self) -> bool:
        return any(item.outcome in PROBLEM_OUTCOMES for item in self.items)


class BatchService:
    def __init__(self, receipts: ReceiptService) -> None:
        self.receipts = receipts

    def submit(self, text: str) -> BatchView:
        rows = split_rows(text)
        if not rows:
            raise InvalidBatchError("the batch has no receipts")
        if len(rows) > MAX_ROWS:
            raise InvalidBatchError(f"a batch has at most {MAX_ROWS} receipts, got {len(rows)}")
        now = self.receipts.clock()
        batch_id = "bat_" + hashlib.sha256(f"{text}|{now.isoformat()}".encode()).hexdigest()[:8]
        items: list[BatchItemRecord] = []
        seen: set[str] = set()
        for number, raw in enumerate(rows, start=1):
            items.append(self._submit_row(number, raw, batch_id, seen))
        with self.receipts.store.transaction() as tx:
            tx.add_batch(batch_id, items, now)
        return self.get(batch_id)

    def _submit_row(self, number: int, raw: str, batch_id: str, seen: set[str]) -> BatchItemRecord:
        try:
            receipt = parse_receipt(raw)
        except InvalidReceiptError as exc:
            return BatchItemRecord(number, None, "invalid", exc.message)
        if receipt.receipt_id in seen:
            return BatchItemRecord(
                number,
                receipt.receipt_id,
                "duplicate_in_batch",
                f"duplicate receipt_id {receipt.receipt_id} in this batch",
            )
        seen.add(receipt.receipt_id)
        try:
            outcome = self.receipts.submit_parsed(receipt, None, batch_id)
        except AppError as exc:
            return BatchItemRecord(number, receipt.receipt_id, "invalid", exc.message)
        return BatchItemRecord(number, outcome.receipt_id, outcome.outcome, None)

    def get(self, batch_id: str) -> BatchView:
        with self.receipts.store.transaction(write=False) as tx:
            batch = tx.get_batch(batch_id)
            if batch is None:
                raise NotFoundError(f"no batch {batch_id!r}")
            counts = tx.batch_state_counts(batch_id)
            states = {
                item.receipt_id: record.state
                for item in batch.items
                if item.receipt_id is not None
                and (record := tx.get_receipt(item.receipt_id)) is not None
            }
        items = tuple(
            BatchItemView(
                row=i.row,
                receipt_id=i.receipt_id,
                outcome=i.outcome,
                error=i.error,
                state=states.get(i.receipt_id) if i.receipt_id else None,
            )
            for i in batch.items
        )
        return BatchView(batch_id, batch.total, batch.created_at, counts, items)
