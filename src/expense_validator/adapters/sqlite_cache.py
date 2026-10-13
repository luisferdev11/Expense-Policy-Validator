"""The classification answer cache as a table of the store's database (spec 006, research R3, R4).

One row per cache key, written with `INSERT ... ON CONFLICT DO NOTHING` in its own short
transaction, so any number of workers that share the database file share the answers, and a billed
answer is durable the moment `put` returns. The committed `outputs/classifications.jsonl` stays
the reproducibility artifact: the table is seeded from it when empty and `export_lines` writes it
back byte for byte. Rows keep the whole `CacheEntry` as JSON; the other columns are copies for
queries.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import closing, contextmanager
from pathlib import Path

from expense_validator.adapters.sqlite_store import BUSY_TIMEOUT_MS
from expense_validator.domain.models import CacheEntry
from expense_validator.ports.store import Clock, stamp


class SqliteClassificationCache:
    """Satisfies `ClassificationCachePort`. The database must already be at schema 2 (a
    `SqliteStore` on the same file creates the table)."""

    def __init__(self, path: Path, clock: Clock) -> None:
        self.path = path
        self._clock = clock

    @contextmanager
    def _write(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path, timeout=BUSY_TIMEOUT_MS / 1000, isolation_level=None)
        try:
            conn.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS}")
            conn.execute("BEGIN IMMEDIATE")
            try:
                yield conn
            except BaseException:
                conn.execute("ROLLBACK")
                raise
            conn.execute("COMMIT")
        finally:
            conn.close()

    def _insert(self, conn: sqlite3.Connection, entry: CacheEntry, seeded: bool) -> bool:
        cursor = conn.execute(
            "INSERT INTO classification_cache (cache_key, entry, model_id, prompt_version,"
            " cost_usd, seeded, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)"
            " ON CONFLICT (cache_key) DO NOTHING",
            (
                entry.cache_key,
                entry.model_dump_json(),
                entry.model_id,
                entry.prompt_version,
                entry.cost_usd,
                int(seeded),
                stamp(self._clock()),
            ),
        )
        return cursor.rowcount == 1

    def get(self, key: str) -> CacheEntry | None:
        with closing(sqlite3.connect(self.path, timeout=BUSY_TIMEOUT_MS / 1000)) as conn:
            row = conn.execute(
                "SELECT entry FROM classification_cache WHERE cache_key = ?", (key,)
            ).fetchone()
        return None if row is None else CacheEntry.model_validate_json(row[0])

    def put(self, entry: CacheEntry) -> bool:
        with self._write() as conn:
            return self._insert(conn, entry, seeded=False)

    def __len__(self) -> int:
        with closing(sqlite3.connect(self.path, timeout=BUSY_TIMEOUT_MS / 1000)) as conn:
            return int(conn.execute("SELECT COUNT(*) FROM classification_cache").fetchone()[0])

    def seed_from(self, path: Path) -> int:
        """Insert every row of a JSONL file when the table is empty; otherwise do nothing.

        Returns the number of rows inserted. A missing file seeds nothing. The check and the
        inserts share one transaction, so two processes starting together seed it once.
        """
        if not path.exists():
            return 0
        entries = [
            CacheEntry.model_validate_json(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        with self._write() as conn:
            if conn.execute("SELECT COUNT(*) FROM classification_cache").fetchone()[0]:
                return 0
            return sum(self._insert(conn, entry, seeded=True) for entry in entries)

    def export_lines(self) -> Iterator[str]:
        """The rows sorted by key, each as `ClassificationCache.save` writes it (no newline)."""
        with closing(sqlite3.connect(self.path, timeout=BUSY_TIMEOUT_MS / 1000)) as conn:
            rows = conn.execute("SELECT entry FROM classification_cache ORDER BY cache_key")
            for (text,) in rows.fetchall():
                entry = CacheEntry.model_validate_json(text)
                yield json.dumps(entry.model_dump(mode="json"), ensure_ascii=False)
