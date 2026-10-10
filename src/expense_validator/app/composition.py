"""Composition root of the backend: where the store, the clock and the services are wired.

The API process and the worker process each call this, so they share one database file and
nothing else (ADR 0007 D13).
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path

from expense_validator.adapters.sqlite_store import SqliteStore, utc_now
from expense_validator.app.service import ReceiptService
from expense_validator.paths import DEFAULT_DB_FILE


def db_path(explicit: str | None = None, env: Mapping[str, str] | None = None) -> Path:
    """The database file: the flag, else `EPV_DB`, else `var/epv.sqlite3`."""
    env = os.environ if env is None else env
    chosen = explicit or env.get("EPV_DB")
    return Path(chosen) if chosen else DEFAULT_DB_FILE


def open_store(path: Path) -> SqliteStore:
    return SqliteStore(path)


def build_service(store: SqliteStore) -> ReceiptService:
    return ReceiptService(store, utc_now)
