"""The SQLite store against a temporary file (ADR 0007 D1, data-model.md)."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from expense_validator.adapters import sqlite_store
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
V1_FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "schema_v1.sql"


@pytest.fixture
def store(tmp_path: Path) -> SqliteStore:
    return SqliteStore(tmp_path / "epv.sqlite3")


def _v1_database(tmp_path: Path) -> Path:
    """A schema-1 file with five receipts, built by the v0.4.0 code (`schema_v1.sql`)."""
    path = tmp_path / "v1.sqlite3"
    with closing(sqlite3.connect(path)) as conn:
        conn.executescript(V1_FIXTURE.read_text(encoding="utf-8"))
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 1
    return path


def _columns(path: Path, table: str) -> set[str]:
    with closing(sqlite3.connect(path)) as conn:
        return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def _version(path: Path) -> int:
    with closing(sqlite3.connect(path)) as conn:
        return int(conn.execute("PRAGMA user_version").fetchone()[0])


def _record(
    receipt_id: str = "R-1",
    revision: int = 1,
    state: str = "submitted",
    created_at: str = "2026-10-10T12:00:00.000000+00:00",
    updated_at: str = "2026-10-10T12:00:00.000000+00:00",
) -> ReceiptRecord:
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
        updated_at=updated_at,
        created_at=created_at,
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


def test_a_fresh_file_is_schema_two_with_the_cache_table_and_the_new_columns(
    tmp_path: Path,
) -> None:
    path = tmp_path / "fresh.sqlite3"
    assert SqliteStore(path).schema_version == 2
    assert _version(path) == 2
    assert {"created_at", "decided_by", "decided_at"} <= _columns(path, "receipts")
    assert _columns(path, "classification_cache") == {
        "cache_key",
        "entry",
        "model_id",
        "prompt_version",
        "cost_usd",
        "seeded",
        "created_at",
    }
    with closing(sqlite3.connect(path)) as conn:
        indexes = {row[1] for row in conn.execute("PRAGMA index_list(receipts)")}
    assert {"receipts_created", "receipts_updated"} <= indexes


def test_a_schema_one_file_is_migrated_to_two_in_place(tmp_path: Path) -> None:
    path = _v1_database(tmp_path)
    assert SqliteStore(path).schema_version == 2
    assert _version(path) == 2
    assert {"created_at", "decided_by", "decided_at"} <= _columns(path, "receipts")
    with closing(sqlite3.connect(path)) as conn:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert "classification_cache" in tables
        assert conn.execute("SELECT COUNT(*) FROM receipts").fetchone()[0] == 5
        assert conn.execute("SELECT COUNT(*) FROM events").fetchone()[0] > 5


def test_a_migration_step_that_fails_leaves_schema_one_and_the_data_intact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _v1_database(tmp_path)

    def broken(conn: sqlite3.Connection) -> None:
        conn.execute("ALTER TABLE receipts ADD COLUMN created_at TEXT NOT NULL DEFAULT ''")
        raise RuntimeError("step failed")

    monkeypatch.setattr(sqlite_store, "MIGRATIONS", [(2, broken)])
    with pytest.raises(RuntimeError, match="step failed"):
        SqliteStore(path)
    assert _version(path) == 1
    assert "created_at" not in _columns(path, "receipts")
    with closing(sqlite3.connect(path)) as conn:
        assert conn.execute("SELECT COUNT(*) FROM receipts").fetchone()[0] == 5


def test_a_schema_three_file_is_still_refused(tmp_path: Path) -> None:
    path = tmp_path / "three.sqlite3"
    with closing(sqlite3.connect(path)) as conn:
        conn.execute("PRAGMA user_version = 3")
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


def test_the_outbox_holds_at_most_one_pending_item_per_stage(store: SqliteStore) -> None:
    with store.transaction() as tx:
        assert tx.enqueue("R-1", 1, "classify", T0) is True
        assert tx.enqueue("R-1", 1, "classify", T0) is False
        assert tx.enqueue("R-1", 1, "evaluate", T0) is True
        assert tx.open_work_count() == 2


def test_work_can_be_queued_again_while_the_same_stage_is_running(store: SqliteStore) -> None:
    """A change that lands while an evaluation runs must not be lost: the running evaluation may
    have read the state before it, so a new one has to follow."""
    with store.transaction() as tx:
        tx.enqueue("R-1", 1, "evaluate", T0)
        assert tx.claim_work(T0, T0 + timedelta(seconds=60)) is not None
        assert tx.enqueue("R-1", 1, "evaluate", T0) is True
        assert tx.enqueue("R-1", 1, "evaluate", T0) is False


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


def test_created_at_is_written_once_and_an_upsert_never_changes_it(store: SqliteStore) -> None:
    first = "2026-10-10T12:00:00.000000+00:00"
    later = "2026-10-10T12:30:00.000000+00:00"
    with store.transaction() as tx:
        tx.put_receipt(_record("R-1", created_at=first, updated_at=first))
        tx.put_receipt(_record("R-1", state="in_review", created_at=later, updated_at=later))
        found = tx.get_receipt("R-1")
    assert found is not None
    assert (found.created_at, found.updated_at, found.state) == (first, later, "in_review")


def test_the_list_orders_by_a_whitelisted_column_with_the_id_as_tiebreak(
    store: SqliteStore,
) -> None:
    def at(minute: int) -> str:
        return f"2026-10-10T12:{minute:02d}:00.000000+00:00"

    with store.transaction() as tx:
        tx.put_receipt(_record("R-1", created_at=at(3), updated_at=at(1)))
        tx.put_receipt(_record("R-2", created_at=at(1), updated_at=at(3)))
        tx.put_receipt(_record("R-3", created_at=at(1), updated_at=at(2)))
        by = {
            order: [r.receipt_id for r in tx.list_receipts(order=order)[0]]  # type: ignore[arg-type]
            for order in ("receipt_id", "created_at", "updated_at")
        }
        with pytest.raises(ValueError, match="order"):
            tx.list_receipts(order="receipt_id; DROP TABLE receipts")  # type: ignore[arg-type]
    assert by == {
        "receipt_id": ["R-1", "R-2", "R-3"],
        "created_at": ["R-2", "R-3", "R-1"],  # R-2 and R-3 tie on time: the id decides
        "updated_at": ["R-1", "R-3", "R-2"],
    }


# Backfill of schema 1 -> 2 (data-model.md sections 3.3 and 3.4)


def _first_revision_times(path: Path) -> dict[str, str]:
    with closing(sqlite3.connect(path)) as conn:
        rows = conn.execute("SELECT receipt_id, MIN(created_at) FROM revisions GROUP BY receipt_id")
        return dict(rows.fetchall())


def test_the_migration_dates_each_receipt_from_its_earliest_revision(tmp_path: Path) -> None:
    path = _v1_database(tmp_path)
    expected = _first_revision_times(path)
    assert set(expected) == {"R-A", "R-B", "R-C", "R-D", "R-E"}
    SqliteStore(path)
    with closing(sqlite3.connect(path)) as conn:
        found = dict(conn.execute("SELECT receipt_id, created_at FROM receipts").fetchall())
    assert found == expected
    assert all(len(text) == 32 for text in found.values())


def test_the_migration_rewrites_every_updated_at_to_one_format_and_keeps_the_instant(
    tmp_path: Path,
) -> None:
    path = _v1_database(tmp_path)
    with closing(sqlite3.connect(path)) as conn:
        before = dict(conn.execute("SELECT receipt_id, updated_at FROM receipts").fetchall())
    assert {len(text) for text in before.values()} != {32}  # the fixture mixes formats
    SqliteStore(path)
    with closing(sqlite3.connect(path)) as conn:
        after = dict(conn.execute("SELECT receipt_id, updated_at FROM receipts").fetchall())
    assert {len(text) for text in after.values()} == {32}
    for receipt_id, old in before.items():
        assert datetime.fromisoformat(after[receipt_id]) == datetime.fromisoformat(old)


def test_a_missing_first_revision_falls_back_to_the_earliest_that_remains(tmp_path: Path) -> None:
    path = _v1_database(tmp_path)
    with closing(sqlite3.connect(path)) as conn:
        second = conn.execute(
            "SELECT created_at FROM revisions WHERE receipt_id = 'R-B' AND revision = 2"
        ).fetchone()[0]
        conn.execute("DELETE FROM revisions WHERE receipt_id = 'R-B' AND revision = 1")
        conn.commit()
    SqliteStore(path)
    with closing(sqlite3.connect(path)) as conn:
        found = conn.execute("SELECT created_at FROM receipts WHERE receipt_id = 'R-B'")
        assert found.fetchone()[0] == second


def test_a_receipt_with_no_revision_stops_the_migration_and_leaves_schema_one(
    tmp_path: Path,
) -> None:
    path = _v1_database(tmp_path)
    with closing(sqlite3.connect(path)) as conn:
        conn.execute("DELETE FROM revisions WHERE receipt_id = 'R-D'")
        conn.commit()
    with pytest.raises(sqlite_store.MigrationError, match="R-D"):
        SqliteStore(path)
    assert _version(path) == 1
    assert "created_at" not in _columns(path, "receipts")


def test_the_migration_backfills_who_decided_and_when_from_the_events(tmp_path: Path) -> None:
    path = _v1_database(tmp_path)
    with closing(sqlite3.connect(path)) as conn:

        def event_time(receipt_id: str, kind: str) -> str:
            row = conn.execute(
                "SELECT at FROM events WHERE receipt_id = ? AND type = ? ORDER BY seq DESC",
                (receipt_id, kind),
            ).fetchone()
            return str(row[0])

        evaluated = conn.execute(
            "SELECT MAX(created_at) FROM evaluations WHERE receipt_id = 'R-D' AND revision = 1"
        ).fetchone()[0]
        expected = {
            "R-A": (None, None),
            "R-B": (None, None),
            "R-C": ("alice", event_time("R-C", "ReceiptApproved")),
            "R-D": ("system", evaluated),
            "R-E": ("bob", event_time("R-E", "ReceiptRejected")),
        }
    SqliteStore(path)
    with closing(sqlite3.connect(path)) as conn:
        found = {
            r[0]: (r[1], r[2])
            for r in conn.execute("SELECT receipt_id, decided_by, decided_at FROM receipts")
        }
    assert found == expected


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
