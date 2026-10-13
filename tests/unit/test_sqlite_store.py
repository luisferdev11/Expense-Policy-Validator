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
    ShadowRecord,
    StoreTx,
    SubmissionRecord,
    stamp,
)
from tests.factories import cls, receipt

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


def test_a_fresh_file_has_the_cache_table_and_the_schema_two_columns(
    tmp_path: Path,
) -> None:
    path = tmp_path / "fresh.sqlite3"
    assert SqliteStore(path).schema_version == SCHEMA_VERSION == 3
    assert _version(path) == 3
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


def test_a_schema_one_file_is_migrated_in_place_through_every_step(tmp_path: Path) -> None:
    path = _v1_database(tmp_path)
    assert SqliteStore(path).schema_version == SCHEMA_VERSION
    assert _version(path) == SCHEMA_VERSION
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


def test_a_schema_four_file_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "four.sqlite3"
    with closing(sqlite3.connect(path)) as conn:
        conn.execute("PRAGMA user_version = 4")
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


# Schema 3 (spec 007): the `shadow` stage in the outbox and the shadow table


V2_FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "schema_v2.sql"


def _v2_database(tmp_path: Path, name: str = "v2.sqlite3") -> Path:
    """A schema-2 file (spec 006's end state) with a pending, a claimed and a done outbox item,
    the done one holding the highest id (`schema_v2.sql`)."""
    path = tmp_path / name
    with closing(sqlite3.connect(path)) as conn:
        conn.executescript(V2_FIXTURE.read_text(encoding="utf-8"))
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 2
    return path


def _master(path: Path) -> list[tuple[str, str, str, str]]:
    """Every table, index and trigger with its SQL text, in a stable order."""
    with closing(sqlite3.connect(path)) as conn:
        return [
            (r[0], r[1], r[2], r[3])
            for r in conn.execute(
                "SELECT type, name, tbl_name, sql FROM sqlite_master"
                " WHERE name NOT LIKE 'sqlite_%' ORDER BY type, name"
            )
        ]


def _outbox(path: Path) -> list[tuple[object, ...]]:
    with closing(sqlite3.connect(path)) as conn:
        return conn.execute("SELECT * FROM outbox ORDER BY id").fetchall()


def test_the_v2_to_v3_migration_keeps_every_outbox_row_and_id(tmp_path: Path) -> None:
    path = _v2_database(tmp_path)
    before = _outbox(path)
    assert [row[4] for row in before] == ["pending", "claimed", "done"]
    assert SqliteStore(path).schema_version == 3
    assert _version(path) == 3
    assert _outbox(path) == before


def test_the_rebuilt_outbox_allows_the_shadow_stage_and_keeps_its_guards(tmp_path: Path) -> None:
    path = _v2_database(tmp_path)
    store = SqliteStore(path)
    with store.transaction() as tx:
        assert tx.enqueue("R-A", 1, "shadow", T0) is True
        assert tx.enqueue("R-A", 1, "shadow", T0) is False  # outbox_open still refuses a duplicate
        assert tx.enqueue("R-A", 1, "classify", T0) is False  # R-A's classify is still pending
    with closing(sqlite3.connect(path)) as conn, pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO outbox (receipt_id, revision, stage, state, created_at)"
            " VALUES ('R-Z', 1, 'bogus', 'pending', 'x')"
        )
    with closing(sqlite3.connect(path)) as conn:
        names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")}
    assert "outbox_open" in names


def test_new_outbox_ids_continue_above_the_old_maximum_and_the_pending_item_is_claimable(
    tmp_path: Path,
) -> None:
    path = _v2_database(tmp_path)
    store = SqliteStore(path)
    with store.transaction() as tx:
        tx.enqueue("R-N", 1, "shadow", T0)
        claimed = tx.claim_work(T0, T0 + timedelta(seconds=60))
    assert claimed is not None and (claimed.id, claimed.receipt_id) == (1, "R-A")  # the old one
    new_ids = [row[0] for row in _outbox(path) if row[1] == "R-N"]
    assert new_ids == [4]  # above the highest id the migration found (3)


def test_the_migration_creates_the_shadow_table_and_its_index(tmp_path: Path) -> None:
    path = _v2_database(tmp_path)
    SqliteStore(path)
    assert _columns(path, "shadow_classifications") == {
        "receipt_id",
        "revision",
        "line_id",
        "classifier",
        "model_id",
        "prompt_version",
        "status",
        "payload",
        "created_at",
    }
    with closing(sqlite3.connect(path)) as conn:
        indexes = {r[1] for r in conn.execute("PRAGMA index_list(shadow_classifications)")}
    assert "shadow_by_classifier" in indexes


def test_a_fresh_v3_file_and_a_migrated_one_have_the_same_schema(tmp_path: Path) -> None:
    fresh = tmp_path / "fresh.sqlite3"
    SqliteStore(fresh)
    migrated = _v2_database(tmp_path)
    SqliteStore(migrated)
    assert _master(migrated) == _master(fresh)


def test_a_v1_file_migrated_through_both_steps_has_the_v3_tables(tmp_path: Path) -> None:
    path = _v1_database(tmp_path)
    SqliteStore(path)
    names = {row[1] for row in _master(path) if row[0] == "table"}
    assert {"shadow_classifications", "classification_cache", "outbox"} <= names
    with closing(sqlite3.connect(path)) as conn:
        sql = conn.execute("SELECT sql FROM sqlite_master WHERE name = 'outbox'").fetchone()[0]
    assert "'shadow'" in sql


def test_a_failure_in_the_v3_step_leaves_the_database_at_v2_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _v2_database(tmp_path)
    before_master, before_rows = _master(path), _outbox(path)

    def broken(conn: sqlite3.Connection) -> None:
        sqlite_store._migrate_2_to_3(conn)  # the whole step runs, then fails
        raise RuntimeError("step failed")

    monkeypatch.setattr(sqlite_store, "MIGRATIONS", [*sqlite_store.MIGRATIONS[:1], (3, broken)])
    with pytest.raises(RuntimeError, match="step failed"):
        SqliteStore(path)
    assert _version(path) == 2
    assert _master(path) == before_master
    assert _outbox(path) == before_rows


def _shadow_rows(receipt_id: str = "R-1", revision: int = 1, n: int = 2) -> list[ShadowRecord]:
    return [
        ShadowRecord(
            receipt_id=receipt_id,
            revision=revision,
            line_id=f"{receipt_id}-L{i}",
            classifier="jev-hybrid",
            model_id="typesafe/jev-1.13+openai/gpt-oss-120b",
            prompt_version="hyb-v1(dec-v1+cls-v2)",
            classification=cls(f"{receipt_id}-L{i}", "alcohol"),
            created_at=stamp(T0),
        )
        for i in range(1, n + 1)
    ]


def test_saving_shadow_rows_is_idempotent(store: SqliteStore) -> None:
    rows = _shadow_rows()
    with store.transaction() as tx:
        tx.save_shadow(rows)
        tx.save_shadow(rows)
        tx.save_shadow(_shadow_rows())  # an equal batch built again
        assert tx.shadow_for("R-1", 1) == rows


def test_a_second_answer_for_the_same_line_does_not_replace_the_first(store: SqliteStore) -> None:
    first = _shadow_rows(n=1)
    other = [
        ShadowRecord(**{**first[0].__dict__, "classification": cls("R-1-L1", "tobacco")})  # type: ignore[arg-type]
    ]
    with store.transaction() as tx:
        tx.save_shadow(first)
        tx.save_shadow(other)
        (kept,) = tx.shadow_for("R-1", 1)
    assert kept.classification.category == "alcohol"


def test_shadow_rows_come_back_for_their_revision_and_in_line_order(store: SqliteStore) -> None:
    with store.transaction() as tx:
        tx.save_shadow(_shadow_rows("R-1", 1, 2))
        tx.save_shadow(_shadow_rows("R-1", 2, 1))
        tx.save_shadow(_shadow_rows("R-2", 1, 1))
        assert [r.line_id for r in tx.shadow_for("R-1", 1)] == ["R-1-L1", "R-1-L2"]
        assert [r.revision for r in tx.shadow_for("R-1", 2)] == [2]
        assert tx.shadow_for("R-9", 1) == []


def test_iter_shadow_filters_by_classifier_in_a_stable_order(store: SqliteStore) -> None:
    hybrid = _shadow_rows("R-1", 1, 1)
    jev = [ShadowRecord(**{**hybrid[0].__dict__, "classifier": "jev-1.13"})]  # type: ignore[arg-type]
    with store.transaction() as tx:
        tx.save_shadow(hybrid)
        tx.save_shadow(jev)
        tx.save_shadow(_shadow_rows("R-2", 1, 1))
        assert [r.classifier for r in tx.iter_shadow("jev-1.13")] == ["jev-1.13"]
        assert len(list(tx.iter_shadow())) == 3
        assert [r.receipt_id for r in tx.iter_shadow("jev-hybrid")] == ["R-1", "R-2"]


def test_shadow_created_at_uses_the_store_format(store: SqliteStore) -> None:
    with store.transaction() as tx:
        tx.save_shadow(_shadow_rows(n=1))
        (row,) = tx.shadow_for("R-1", 1)
    assert len(row.created_at) == 32 and row.created_at.endswith("+00:00")
    assert row.created_at == "2026-10-10T12:00:00.000000+00:00"


def test_a_shadow_outbox_item_is_claimed_leased_and_retried_like_the_others(
    store: SqliteStore,
) -> None:
    with store.transaction() as tx:
        assert tx.enqueue("R-1", 1, "shadow", T0)
        item = tx.claim_work(T0, T0 + timedelta(seconds=60))
    assert item is not None and (item.stage, item.attempts) == ("shadow", 1)
    with store.transaction() as tx:
        assert tx.claim_work(T0 + timedelta(seconds=30), T0 + timedelta(seconds=90)) is None
        again = tx.claim_work(T0 + timedelta(seconds=61), T0 + timedelta(seconds=120))
    assert again is not None and (again.id, again.attempts) == (item.id, 2)
    with store.transaction() as tx:
        tx.complete_work(again.id)
        assert tx.open_work_count() == 0


def test_shadow_work_and_classify_work_for_one_revision_are_separate_items(
    store: SqliteStore,
) -> None:
    with store.transaction() as tx:
        assert tx.enqueue("R-1", 1, "evaluate", T0)
        assert tx.enqueue("R-1", 1, "shadow", T0)
        assert tx.open_work_count() == 2
