"""The SQLite store against a temporary file (ADR 0007 D1, data-model.md)."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from expense_validator.adapters.sqlite_store import (
    SCHEMA_VERSION,
    SchemaTooNewError,
    SqliteStore,
)
from expense_validator.domain.cascade import sharing_keys
from expense_validator.domain.events import ReceiptSubmitted
from expense_validator.domain.idempotency import content_hash
from expense_validator.ports.store import (
    BatchItemRecord,
    ReceiptRecord,
    StoreTx,
    SubmissionRecord,
)
from tests.factories import receipt

T0 = datetime(2026, 10, 10, 12, 0, tzinfo=UTC)


@pytest.fixture
def store(tmp_path: Path) -> SqliteStore:
    return SqliteStore(tmp_path / "epv.sqlite3")


def _record(receipt_id: str = "R-1", revision: int = 1, state: str = "submitted") -> ReceiptRecord:
    return ReceiptRecord(
        receipt_id=receipt_id,
        current_revision=revision,
        state=state,  # type: ignore[arg-type]
        disposition=None,
        evaluation_version=None,
        human_acted=False,
        notice=None,
        qa_sample=False,
        failed_stage=None,
        failed_reason=None,
        updated_at="t",
    )


def _add(tx: StoreTx, receipt_id: str = "R-1", revision: int = 1, **overrides: object) -> None:
    r = receipt(receipt_id=receipt_id, **overrides)
    tx.add_revision(receipt_id, revision, content_hash(r), r, sharing_keys(r), T0)
    tx.put_receipt(_record(receipt_id, revision))


def test_a_new_file_gets_the_schema_version_and_wal(store: SqliteStore, tmp_path: Path) -> None:
    assert store.schema_version == SCHEMA_VERSION
    with sqlite3.connect(tmp_path / "epv.sqlite3") as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
        assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"


def test_a_newer_schema_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "newer.sqlite3"
    with sqlite3.connect(path) as conn:
        conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION + 1}")
    with pytest.raises(SchemaTooNewError):
        SqliteStore(path)


def test_reopening_an_existing_file_keeps_its_data(store: SqliteStore, tmp_path: Path) -> None:
    with store.transaction() as tx:
        _add(tx)
    again = SqliteStore(tmp_path / "epv.sqlite3")
    with again.transaction(write=False) as tx:
        assert tx.get_receipt("R-1") is not None


def test_a_failing_transaction_rolls_everything_back(store: SqliteStore) -> None:
    with pytest.raises(RuntimeError), store.transaction() as tx:
        _add(tx)
        tx.append_event("R-1", 1, ReceiptSubmitted(content_hash="h", idempotency_key="k"), "s", T0)
        tx.enqueue("R-1", 1, "classify", T0)
        raise RuntimeError("boom")
    with store.transaction(write=False) as tx:
        assert tx.get_receipt("R-1") is None
        assert tx.get_revision("R-1", 1) is None
        assert tx.list_events("R-1") == []
        assert tx.open_work_count() == 0


def test_a_revision_round_trips_and_keeps_the_stripped_content(store: SqliteStore) -> None:
    with store.transaction() as tx:
        _add(tx, employee_id="E-9", trip_id="TRIP-1")
    with store.transaction(write=False) as tx:
        found = tx.get_revision("R-1", 1)
        assert found is not None
        assert found.receipt == receipt(receipt_id="R-1", employee_id="E-9", trip_id="TRIP-1")
        assert tx.keys_of_receipt("R-1") == sharing_keys(found.receipt)


@pytest.mark.parametrize("statement", ["UPDATE events SET actor = 'x'", "DELETE FROM events"])
def test_the_event_log_is_append_only(store: SqliteStore, statement: str) -> None:
    with store.transaction() as tx:
        tx.append_event(
            "R-1", 1, ReceiptSubmitted(content_hash="h", idempotency_key="k"), "system", T0
        )
    with (
        closing(sqlite3.connect(store.path)) as conn,
        pytest.raises(sqlite3.DatabaseError, match="append-only"),
    ):
        conn.execute(statement)


def test_events_come_back_in_order_and_typed(store: SqliteStore) -> None:
    with store.transaction() as tx:
        tx.append_event("R-1", 1, ReceiptSubmitted(content_hash="a", idempotency_key="k"), "s", T0)
        tx.append_event("R-1", 1, ReceiptSubmitted(content_hash="b", idempotency_key="k"), "s", T0)
    with store.transaction(write=False) as tx:
        events = tx.list_events("R-1")
    assert [e.event.content_hash for e in events] == ["a", "b"]  # type: ignore[union-attr]
    assert events[0].seq < events[1].seq


def test_a_submission_key_can_be_repointed(store: SqliteStore) -> None:
    first = SubmissionRecord("k", "R-1", 1, "h1", None)
    again = SubmissionRecord("k", "R-1", 2, "h1", None)
    with store.transaction() as tx:
        tx.put_submission(first, T0)
        tx.put_submission(again, T0)
        assert tx.get_submission("k") == again
        assert tx.get_submission("missing") is None


def test_receipts_sharing_a_key_are_found_by_their_current_revision(store: SqliteStore) -> None:
    with store.transaction() as tx:
        _add(tx, "R-1", transaction_datetime="2026-05-01T12:00:00")
        _add(tx, "R-2", transaction_datetime="2026-05-01T19:00:00")
        _add(tx, "R-3", transaction_datetime="2026-05-02T12:00:00")
        keys = sharing_keys(receipt(receipt_id="R-1", transaction_datetime="2026-05-01T12:00:00"))
        assert tx.current_receipts_sharing(keys) == ["R-1", "R-2"]
        assert tx.current_receipts_sharing([]) == []


def test_a_superseded_revision_no_longer_shares_its_old_keys(store: SqliteStore) -> None:
    with store.transaction() as tx:
        _add(tx, "R-1", transaction_datetime="2026-05-01T12:00:00")
        old = sharing_keys(receipt(transaction_datetime="2026-05-01T12:00:00"))
        _add(tx, "R-1", 2, transaction_datetime="2026-05-09T12:00:00")
        tx.mark_superseded("R-1", 1)
        assert tx.current_receipts_sharing(old) == []
        assert tx.keys_of_receipt("R-1") >= old
        assert tx.get_revision("R-1", 1).status == "superseded"  # type: ignore[union-attr]


def test_the_outbox_holds_at_most_one_open_item_per_stage(store: SqliteStore) -> None:
    with store.transaction() as tx:
        assert tx.enqueue("R-1", 1, "classify", T0) is True
        assert tx.enqueue("R-1", 1, "classify", T0) is False
        assert tx.enqueue("R-1", 1, "evaluate", T0) is True
        assert tx.open_work_count() == 2


def test_a_claim_sets_a_lease_and_hands_each_item_out_once(store: SqliteStore) -> None:
    with store.transaction() as tx:
        tx.enqueue("R-1", 1, "classify", T0)
        tx.enqueue("R-2", 1, "classify", T0)
    lease = T0 + timedelta(seconds=60)
    with store.transaction() as tx:
        first = tx.claim_work(T0, lease)
        second = tx.claim_work(T0, lease)
        third = tx.claim_work(T0, lease)
    assert first is not None and second is not None and third is None
    assert (first.receipt_id, second.receipt_id) == ("R-1", "R-2")
    assert first.attempts == 1


def test_an_expired_lease_makes_the_item_claimable_again(store: SqliteStore) -> None:
    with store.transaction() as tx:
        tx.enqueue("R-1", 1, "classify", T0)
        claimed = tx.claim_work(T0, T0 + timedelta(seconds=60))
        assert claimed is not None
        assert tx.claim_work(T0 + timedelta(seconds=59), T0 + timedelta(seconds=120)) is None
        again = tx.claim_work(T0 + timedelta(seconds=61), T0 + timedelta(seconds=120))
    assert again is not None and again.id == claimed.id and again.attempts == 2


def test_two_connections_never_claim_the_same_item(store: SqliteStore, tmp_path: Path) -> None:
    other = SqliteStore(tmp_path / "epv.sqlite3")
    with store.transaction() as tx:
        tx.enqueue("R-1", 1, "classify", T0)
    lease = T0 + timedelta(seconds=60)
    with store.transaction() as tx:
        mine = tx.claim_work(T0, lease)
    with other.transaction() as tx:
        theirs = tx.claim_work(T0, lease)
    assert mine is not None and theirs is None


def test_completed_failed_and_cancelled_items_are_not_claimed(store: SqliteStore) -> None:
    with store.transaction() as tx:
        for n in (1, 2, 3):
            tx.enqueue(f"R-{n}", 1, "classify", T0)
        a = tx.claim_work(T0, T0 + timedelta(seconds=1))
        b = tx.claim_work(T0, T0 + timedelta(seconds=1))
        assert a is not None and b is not None
        tx.complete_work(a.id)
        tx.fail_work(b.id, "boom")
        assert tx.cancel_open_work("R-3", 1) == 1
        assert tx.claim_work(T0 + timedelta(days=1), T0 + timedelta(days=2)) is None
        assert tx.open_work_count() == 0


def test_a_cancelled_stage_can_be_enqueued_again(store: SqliteStore) -> None:
    with store.transaction() as tx:
        tx.enqueue("R-1", 1, "classify", T0)
        tx.cancel_open_work("R-1", 1)
        assert tx.enqueue("R-1", 1, "classify", T0) is True


def test_the_receipt_list_filters_and_counts(store: SqliteStore) -> None:
    with store.transaction() as tx:
        tx.put_receipt(_record("R-1", state="in_review"))
        tx.put_receipt(_record("R-2", state="in_review"))
        tx.put_receipt(_record("R-3", state="approved"))
        items, total = tx.list_receipts(state="in_review", limit=1)
        assert (len(items), total) == (1, 2)
        assert tx.list_receipts()[1] == 3


def test_a_batch_summarises_its_items_by_receipt_state(store: SqliteStore) -> None:
    with store.transaction() as tx:
        tx.put_receipt(_record("R-1", state="in_review"))
        tx.put_receipt(_record("R-2", state="approved"))
        tx.add_batch(
            "bat_1",
            [
                BatchItemRecord(1, "R-1", "accepted", None),
                BatchItemRecord(2, "R-2", "accepted", None),
                BatchItemRecord(3, None, "invalid", "not valid JSON"),
            ],
            T0,
        )
        assert tx.batch_state_counts("bat_1") == {"approved": 1, "in_review": 1, "invalid": 1}
        found = tx.get_batch("bat_1")
        assert found is not None and found.total == 3 and found.items[2].error == "not valid JSON"
        assert tx.list_receipts(batch_id="bat_1")[1] == 2
        assert tx.get_batch("missing") is None
