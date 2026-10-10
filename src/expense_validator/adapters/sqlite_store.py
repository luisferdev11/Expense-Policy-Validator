"""SQLite implementation of the receipt store (ADR 0007 D1, data-model.md).

Stdlib `sqlite3`, no ORM. Every write runs in one `BEGIN IMMEDIATE` transaction, so a
read-modify-write cannot interleave with another writer, and the event, the projection and the
outbox row commit together. WAL mode and a busy timeout let the API and the worker, two
processes, share the file. The log of events is protected from update and delete by triggers.
"""

from __future__ import annotations

import json
import re
import sqlite3
from collections.abc import Collection, Iterator, Sequence
from contextlib import closing, contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from expense_validator.domain.events import Event, event_payload, parse_event
from expense_validator.domain.lifecycle import Stage
from expense_validator.domain.models import (
    Classification,
    ReceiptInput,
    ReceiptResult,
)
from expense_validator.ports.store import (
    BatchItemRecord,
    BatchRecord,
    EvaluationRecord,
    EventRecord,
    ReceiptRecord,
    RevisionRecord,
    SubmissionRecord,
    WorkItem,
)

SCHEMA_VERSION = 1
MIN_SQLITE = (3, 35, 0)  # UPDATE ... RETURNING
BUSY_TIMEOUT_MS = 10_000

_SCHEMA = """
CREATE TABLE revisions (
    receipt_id TEXT NOT NULL,
    revision INTEGER NOT NULL,
    content_hash TEXT NOT NULL,
    content TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('current', 'superseded')),
    created_at TEXT NOT NULL,
    PRIMARY KEY (receipt_id, revision)
);
CREATE TABLE receipt_keys (
    receipt_id TEXT NOT NULL,
    revision INTEGER NOT NULL,
    key TEXT NOT NULL,
    PRIMARY KEY (receipt_id, revision, key)
);
CREATE INDEX receipt_keys_key ON receipt_keys (key);
CREATE TABLE submissions (
    idempotency_key TEXT PRIMARY KEY,
    receipt_id TEXT NOT NULL,
    revision INTEGER NOT NULL,
    content_hash TEXT NOT NULL,
    batch_id TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE receipts (
    receipt_id TEXT PRIMARY KEY,
    current_revision INTEGER NOT NULL,
    state TEXT NOT NULL,
    disposition TEXT,
    evaluation_version INTEGER,
    human_acted INTEGER NOT NULL DEFAULT 0,
    notice TEXT,
    qa_sample INTEGER NOT NULL DEFAULT 0,
    failed_stage TEXT,
    failed_reason TEXT,
    updated_at TEXT NOT NULL
);
CREATE INDEX receipts_state ON receipts (state);
CREATE TABLE classifications (
    receipt_id TEXT NOT NULL,
    revision INTEGER NOT NULL,
    payload TEXT NOT NULL,
    PRIMARY KEY (receipt_id, revision)
);
CREATE TABLE evaluations (
    receipt_id TEXT NOT NULL,
    revision INTEGER NOT NULL,
    version INTEGER NOT NULL,
    result TEXT NOT NULL,
    result_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (receipt_id, revision, version)
);
CREATE TABLE events (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    receipt_id TEXT NOT NULL,
    revision INTEGER NOT NULL,
    type TEXT NOT NULL,
    payload TEXT NOT NULL,
    actor TEXT NOT NULL,
    at TEXT NOT NULL
);
CREATE INDEX events_receipt ON events (receipt_id, seq);
CREATE TRIGGER events_no_update BEFORE UPDATE ON events
BEGIN SELECT RAISE(ABORT, 'events are append-only'); END;
CREATE TRIGGER events_no_delete BEFORE DELETE ON events
BEGIN SELECT RAISE(ABORT, 'events are append-only'); END;
CREATE TABLE outbox (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    receipt_id TEXT NOT NULL,
    revision INTEGER NOT NULL,
    stage TEXT NOT NULL CHECK (stage IN ('classify', 'evaluate')),
    state TEXT NOT NULL CHECK (state IN ('pending', 'claimed', 'done', 'cancelled', 'failed')),
    lease_until TEXT,
    attempts INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    created_at TEXT NOT NULL
);
CREATE UNIQUE INDEX outbox_open ON outbox (receipt_id, revision, stage)
    WHERE state = 'pending';
CREATE TABLE batches (
    batch_id TEXT PRIMARY KEY,
    total INTEGER NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE batch_items (
    batch_id TEXT NOT NULL,
    row INTEGER NOT NULL,
    receipt_id TEXT,
    outcome TEXT NOT NULL,
    error TEXT,
    PRIMARY KEY (batch_id, row)
);
"""


class SchemaTooNewError(Exception):
    """The database was written by a newer version of the application."""


def utc_now() -> datetime:
    return datetime.now(UTC)


def _ts(moment: datetime) -> str:
    """Fixed-width UTC text, so comparisons in SQL are comparisons in time."""
    return moment.astimezone(UTC).isoformat(timespec="microseconds")


def _receipt(row: sqlite3.Row) -> ReceiptRecord:
    return ReceiptRecord(
        receipt_id=row["receipt_id"],
        current_revision=row["current_revision"],
        state=row["state"],
        disposition=row["disposition"],
        evaluation_version=row["evaluation_version"],
        human_acted=bool(row["human_acted"]),
        notice=row["notice"],
        qa_sample=bool(row["qa_sample"]),
        failed_stage=row["failed_stage"],
        failed_reason=row["failed_reason"],
        updated_at=row["updated_at"],
    )


def _evaluation(row: sqlite3.Row) -> EvaluationRecord:
    return EvaluationRecord(
        receipt_id=row["receipt_id"],
        revision=row["revision"],
        version=row["version"],
        result=ReceiptResult.model_validate_json(row["result"]),
        result_hash=row["result_hash"],
        created_at=row["created_at"],
    )


class SqliteTx:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._c = conn

    # Idempotency

    def get_submission(self, key: str) -> SubmissionRecord | None:
        row = self._c.execute("SELECT * FROM submissions WHERE idempotency_key = ?", (key,))
        found = row.fetchone()
        if found is None:
            return None
        return SubmissionRecord(
            idempotency_key=found["idempotency_key"],
            receipt_id=found["receipt_id"],
            revision=found["revision"],
            content_hash=found["content_hash"],
            batch_id=found["batch_id"],
        )

    def put_submission(self, record: SubmissionRecord, now: datetime) -> None:
        self._c.execute(
            "INSERT INTO submissions (idempotency_key, receipt_id, revision, content_hash,"
            " batch_id, created_at) VALUES (?, ?, ?, ?, ?, ?)"
            " ON CONFLICT (idempotency_key) DO UPDATE SET receipt_id = excluded.receipt_id,"
            " revision = excluded.revision, content_hash = excluded.content_hash,"
            " batch_id = excluded.batch_id",
            (
                record.idempotency_key,
                record.receipt_id,
                record.revision,
                record.content_hash,
                record.batch_id,
                _ts(now),
            ),
        )

    # Receipts

    def get_receipt(self, receipt_id: str) -> ReceiptRecord | None:
        row = self._c.execute("SELECT * FROM receipts WHERE receipt_id = ?", (receipt_id,))
        found = row.fetchone()
        return None if found is None else _receipt(found)

    def put_receipt(self, record: ReceiptRecord) -> None:
        self._c.execute(
            "INSERT INTO receipts (receipt_id, current_revision, state, disposition,"
            " evaluation_version, human_acted, notice, qa_sample, failed_stage, failed_reason,"
            " updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
            " ON CONFLICT (receipt_id) DO UPDATE SET current_revision = excluded.current_revision,"
            " state = excluded.state, disposition = excluded.disposition,"
            " evaluation_version = excluded.evaluation_version,"
            " human_acted = excluded.human_acted, notice = excluded.notice,"
            " qa_sample = excluded.qa_sample, failed_stage = excluded.failed_stage,"
            " failed_reason = excluded.failed_reason, updated_at = excluded.updated_at",
            (
                record.receipt_id,
                record.current_revision,
                record.state,
                record.disposition,
                record.evaluation_version,
                int(record.human_acted),
                record.notice,
                int(record.qa_sample),
                record.failed_stage,
                record.failed_reason,
                record.updated_at,
            ),
        )

    def list_receipts(
        self,
        *,
        state: str | None = None,
        disposition: str | None = None,
        batch_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[ReceiptRecord], int]:
        where: list[str] = []
        args: list[Any] = []
        if state is not None:
            where.append("state = ?")
            args.append(state)
        if disposition is not None:
            where.append("disposition = ?")
            args.append(disposition)
        if batch_id is not None:
            where.append("receipt_id IN (SELECT receipt_id FROM batch_items WHERE batch_id = ?)")
            args.append(batch_id)
        clause = f" WHERE {' AND '.join(where)}" if where else ""
        total = self._c.execute(f"SELECT COUNT(*) FROM receipts{clause}", args).fetchone()[0]
        rows = self._c.execute(
            f"SELECT * FROM receipts{clause} ORDER BY receipt_id LIMIT ? OFFSET ?",
            [*args, limit, offset],
        ).fetchall()
        return [_receipt(r) for r in rows], int(total)

    # Revisions

    def add_revision(
        self,
        receipt_id: str,
        revision: int,
        content_hash: str,
        receipt: ReceiptInput,
        keys: Collection[str],
        now: datetime,
    ) -> None:
        self._c.execute(
            "INSERT INTO revisions (receipt_id, revision, content_hash, content, status,"
            " created_at) VALUES (?, ?, ?, ?, 'current', ?)",
            (receipt_id, revision, content_hash, receipt.model_dump_json(), _ts(now)),
        )
        self._c.executemany(
            "INSERT INTO receipt_keys (receipt_id, revision, key) VALUES (?, ?, ?)",
            [(receipt_id, revision, key) for key in sorted(keys)],
        )

    def _revision(self, row: sqlite3.Row) -> RevisionRecord:
        return RevisionRecord(
            receipt_id=row["receipt_id"],
            revision=row["revision"],
            content_hash=row["content_hash"],
            receipt=ReceiptInput.model_validate_json(row["content"]),
            status=row["status"],
            created_at=row["created_at"],
        )

    def get_revision(self, receipt_id: str, revision: int) -> RevisionRecord | None:
        cur = self._c.execute(
            "SELECT * FROM revisions WHERE receipt_id = ? AND revision = ?", (receipt_id, revision)
        )
        row = cur.fetchone()
        return None if row is None else self._revision(row)

    def list_revisions(self, receipt_id: str) -> list[RevisionRecord]:
        cur = self._c.execute(
            "SELECT * FROM revisions WHERE receipt_id = ? ORDER BY revision", (receipt_id,)
        )
        return [self._revision(r) for r in cur.fetchall()]

    def mark_superseded(self, receipt_id: str, revision: int) -> None:
        self._c.execute(
            "UPDATE revisions SET status = 'superseded' WHERE receipt_id = ? AND revision = ?",
            (receipt_id, revision),
        )

    def keys_of_receipt(self, receipt_id: str) -> frozenset[str]:
        cur = self._c.execute(
            "SELECT DISTINCT key FROM receipt_keys WHERE receipt_id = ?", (receipt_id,)
        )
        return frozenset(row["key"] for row in cur.fetchall())

    def current_receipts_sharing(self, keys: Collection[str]) -> list[str]:
        if not keys:
            return []
        marks = ",".join("?" for _ in keys)
        cur = self._c.execute(
            "SELECT DISTINCT k.receipt_id FROM receipt_keys k JOIN receipts r"
            " ON r.receipt_id = k.receipt_id AND r.current_revision = k.revision"
            f" WHERE k.key IN ({marks}) ORDER BY k.receipt_id",
            sorted(keys),
        )
        return [row["receipt_id"] for row in cur.fetchall()]

    # Classifications

    def save_classifications(
        self, receipt_id: str, revision: int, classifications: Sequence[Classification]
    ) -> None:
        payload = json.dumps([c.model_dump(mode="json") for c in classifications])
        self._c.execute(
            "INSERT INTO classifications (receipt_id, revision, payload) VALUES (?, ?, ?)"
            " ON CONFLICT (receipt_id, revision) DO UPDATE SET payload = excluded.payload",
            (receipt_id, revision, payload),
        )

    def load_classifications(
        self, receipt_id: str, revision: int
    ) -> tuple[Classification, ...] | None:
        cur = self._c.execute(
            "SELECT payload FROM classifications WHERE receipt_id = ? AND revision = ?",
            (receipt_id, revision),
        )
        row = cur.fetchone()
        if row is None:
            return None
        return tuple(Classification.model_validate(c) for c in json.loads(row["payload"]))

    # Evaluations

    def add_evaluation(
        self,
        receipt_id: str,
        revision: int,
        result: ReceiptResult,
        result_hash: str,
        now: datetime,
    ) -> int:
        cur = self._c.execute(
            "SELECT COALESCE(MAX(version), 0) + 1 FROM evaluations"
            " WHERE receipt_id = ? AND revision = ?",
            (receipt_id, revision),
        )
        version = int(cur.fetchone()[0])
        self._c.execute(
            "INSERT INTO evaluations (receipt_id, revision, version, result, result_hash,"
            " created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (receipt_id, revision, version, result.model_dump_json(), result_hash, _ts(now)),
        )
        return version

    def latest_evaluation(self, receipt_id: str, revision: int) -> EvaluationRecord | None:
        cur = self._c.execute(
            "SELECT * FROM evaluations WHERE receipt_id = ? AND revision = ?"
            " ORDER BY version DESC LIMIT 1",
            (receipt_id, revision),
        )
        row = cur.fetchone()
        return None if row is None else _evaluation(row)

    def list_evaluations(self, receipt_id: str, revision: int) -> list[EvaluationRecord]:
        cur = self._c.execute(
            "SELECT * FROM evaluations WHERE receipt_id = ? AND revision = ? ORDER BY version",
            (receipt_id, revision),
        )
        return [_evaluation(r) for r in cur.fetchall()]

    # Events

    def append_event(
        self, receipt_id: str, revision: int, event: Event, actor: str, now: datetime
    ) -> int:
        cur = self._c.execute(
            "INSERT INTO events (receipt_id, revision, type, payload, actor, at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (receipt_id, revision, event.type, event_payload(event), actor, _ts(now)),
        )
        assert cur.lastrowid is not None
        return cur.lastrowid

    def list_events(self, receipt_id: str) -> list[EventRecord]:
        cur = self._c.execute(
            "SELECT * FROM events WHERE receipt_id = ? ORDER BY seq", (receipt_id,)
        )
        return [
            EventRecord(
                seq=r["seq"],
                receipt_id=r["receipt_id"],
                revision=r["revision"],
                event=parse_event(r["type"], r["payload"]),
                actor=r["actor"],
                at=r["at"],
            )
            for r in cur.fetchall()
        ]

    # Outbox

    def enqueue(self, receipt_id: str, revision: int, stage: Stage, now: datetime) -> bool:
        cur = self._c.execute(
            "INSERT OR IGNORE INTO outbox (receipt_id, revision, stage, state, created_at)"
            " VALUES (?, ?, ?, 'pending', ?)",
            (receipt_id, revision, stage, _ts(now)),
        )
        return cur.rowcount == 1

    def cancel_open_work(self, receipt_id: str, revision: int) -> int:
        cur = self._c.execute(
            "UPDATE outbox SET state = 'cancelled', lease_until = NULL"
            " WHERE receipt_id = ? AND revision = ? AND state IN ('pending', 'claimed')",
            (receipt_id, revision),
        )
        return cur.rowcount

    def claim_work(self, now: datetime, lease_until: datetime) -> WorkItem | None:
        cur = self._c.execute(
            "UPDATE outbox SET state = 'claimed', lease_until = ?, attempts = attempts + 1"
            " WHERE id = (SELECT id FROM outbox WHERE state = 'pending'"
            " OR (state = 'claimed' AND lease_until <= ?) ORDER BY id LIMIT 1)"
            " RETURNING id, receipt_id, revision, stage, attempts",
            (_ts(lease_until), _ts(now)),
        )
        row = cur.fetchone()
        if row is None:
            return None
        return WorkItem(
            id=row["id"],
            receipt_id=row["receipt_id"],
            revision=row["revision"],
            stage=row["stage"],
            attempts=row["attempts"],
        )

    def complete_work(self, item_id: int) -> None:
        self._c.execute(
            "UPDATE outbox SET state = 'done', lease_until = NULL WHERE id = ?", (item_id,)
        )

    def fail_work(self, item_id: int, error: str) -> None:
        self._c.execute(
            "UPDATE outbox SET state = 'failed', lease_until = NULL, last_error = ? WHERE id = ?",
            (error[:500], item_id),
        )

    def open_work_count(self) -> int:
        cur = self._c.execute("SELECT COUNT(*) FROM outbox WHERE state IN ('pending', 'claimed')")
        return int(cur.fetchone()[0])

    # Batches

    def add_batch(self, batch_id: str, items: Sequence[BatchItemRecord], now: datetime) -> None:
        self._c.execute(
            "INSERT INTO batches (batch_id, total, created_at) VALUES (?, ?, ?)",
            (batch_id, len(items), _ts(now)),
        )
        self._c.executemany(
            "INSERT INTO batch_items (batch_id, row, receipt_id, outcome, error)"
            " VALUES (?, ?, ?, ?, ?)",
            [(batch_id, i.row, i.receipt_id, i.outcome, i.error) for i in items],
        )

    def get_batch(self, batch_id: str) -> BatchRecord | None:
        head = self._c.execute("SELECT * FROM batches WHERE batch_id = ?", (batch_id,)).fetchone()
        if head is None:
            return None
        rows = self._c.execute(
            "SELECT * FROM batch_items WHERE batch_id = ? ORDER BY row", (batch_id,)
        ).fetchall()
        return BatchRecord(
            batch_id=batch_id,
            total=head["total"],
            created_at=head["created_at"],
            items=tuple(
                BatchItemRecord(r["row"], r["receipt_id"], r["outcome"], r["error"]) for r in rows
            ),
        )

    def batch_state_counts(self, batch_id: str) -> dict[str, int]:
        cur = self._c.execute(
            "SELECT COALESCE(r.state, 'invalid') AS state, COUNT(*) AS n FROM batch_items b"
            " LEFT JOIN receipts r ON r.receipt_id = b.receipt_id"
            " WHERE b.batch_id = ? GROUP BY COALESCE(r.state, 'invalid') ORDER BY state",
            (batch_id,),
        )
        return {row["state"]: row["n"] for row in cur.fetchall()}


class SqliteStore:
    """One file. Each transaction opens its own connection, so threads and processes are safe."""

    def __init__(self, path: Path) -> None:
        if sqlite3.sqlite_version_info < MIN_SQLITE:
            raise RuntimeError(f"SQLite 3.35 or later is required, found {sqlite3.sqlite_version}")
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self._version = self._init_schema()

    @property
    def schema_version(self) -> int:
        return self._version

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=BUSY_TIMEOUT_MS / 1000, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS}")
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _init_schema(self) -> int:
        with closing(self._connect()) as conn:
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("BEGIN IMMEDIATE")
            try:
                found = int(conn.execute("PRAGMA user_version").fetchone()[0])
                if found > SCHEMA_VERSION:
                    raise SchemaTooNewError(
                        f"database schema {found} is newer than this application ({SCHEMA_VERSION})"
                    )
                if found == 0:
                    for statement in _split(_SCHEMA):
                        conn.execute(statement)
                    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
                conn.execute("COMMIT")
            except BaseException:
                conn.execute("ROLLBACK")
                raise
            return SCHEMA_VERSION

    @contextmanager
    def transaction(self, *, write: bool = True) -> Iterator[SqliteTx]:
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            try:
                yield SqliteTx(conn)
            except BaseException:
                conn.execute("ROLLBACK")
                raise
            conn.execute("COMMIT")
        finally:
            conn.close()


def _split(script: str) -> list[str]:
    """Statements of the schema. Every statement starts a line with CREATE; a trigger body holds
    semicolons, so splitting on every semicolon would cut it."""
    return [part.strip() for part in re.split(r";\n(?=CREATE)", script.strip()) if part.strip()]
