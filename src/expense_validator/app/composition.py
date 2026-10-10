"""Composition root of the backend: where the store, the clock and the services are wired.

The API process and the worker process each call this, so they share one database file and
nothing else (ADR 0007 D13).
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from expense_validator.adapters.config_files import load_pipeline_config, load_settings
from expense_validator.adapters.openrouter.prompt_sync import sync_prompt
from expense_validator.adapters.persisting_classifier import PersistingClassifier
from expense_validator.adapters.sqlite_store import SqliteStore, utc_now
from expense_validator.adapters.tracing import make_tracer
from expense_validator.app.intake import default_classifier
from expense_validator.app.reviewing import ReviewService
from expense_validator.app.service import ReceiptService
from expense_validator.app.worker import Worker
from expense_validator.paths import APP_CLASSIFICATION_CACHE, DEFAULT_DB_FILE


def db_path(explicit: str | None = None, env: Mapping[str, str] | None = None) -> Path:
    """The database file: the flag, else `EPV_DB`, else `var/epv.sqlite3`."""
    env = os.environ if env is None else env
    chosen = explicit or env.get("EPV_DB")
    return Path(chosen) if chosen else DEFAULT_DB_FILE


def open_store(path: Path) -> SqliteStore:
    return SqliteStore(path)


def build_service(store: SqliteStore) -> ReceiptService:
    return ReceiptService(store, utc_now)


def openapi_document() -> dict[str, Any]:
    """The API's OpenAPI document. It is built over a throwaway database, because the routes
    need a service to be created, and nothing is written to the real one."""
    from expense_validator.app.api import create_app

    with tempfile.TemporaryDirectory() as directory:
        store = open_store(Path(directory) / "openapi.sqlite3")
        document: dict[str, Any] = create_app(build_service(store)).openapi()
    return document


def build_review(
    store: SqliteStore, service: ReceiptService, *, no_trace: bool = False
) -> ReviewService:
    """Reviewer actions, scored in Langfuse when it is reachable (best effort)."""
    return ReviewService(
        store, utc_now, service, tracer=make_tracer(disabled=no_trace), settings=load_settings()
    )


def build_worker(
    store: SqliteStore,
    *,
    offline: bool = False,
    no_trace: bool = False,
    cache_path: Path = APP_CLASSIFICATION_CACHE,
) -> Worker:
    """The worker with the configured classifier on the application's own answer cache.

    The cache is gitignored and seeded from the committed one, so the application never changes
    committed outputs, and it is saved after every billed call (see `PersistingClassifier`).
    Langfuse is best effort: with no keys or no server the worker runs untraced.
    """
    tracer = make_tracer(disabled=no_trace)
    prompt_link = None if offline else sync_prompt(tracer)
    base = default_classifier(tracer, cache_path, offline=offline, prompt_link=prompt_link)
    classifier = PersistingClassifier(base, base.cache.save)
    return Worker(store, classifier, tracer, load_settings(), utc_now, load_pipeline_config())
