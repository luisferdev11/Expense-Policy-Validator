"""Composition root of the backend: where the store, the clock and the services are wired.

The API process and the worker process each call this, so they share one database file and
nothing else (ADR 0007 D13).
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from expense_validator.adapters.config_files import load_pipeline_config, load_settings
from expense_validator.adapters.keyword_classifier import KeywordClassifier
from expense_validator.adapters.openrouter.classifier import CAP_USD
from expense_validator.adapters.simulated_classifier import LatencyClassifier, SimulatedClassifier
from expense_validator.adapters.sqlite_cache import SqliteClassificationCache
from expense_validator.adapters.sqlite_store import SqliteStore, utc_now
from expense_validator.adapters.tracing import make_tracer
from expense_validator.app.api import DEFAULT_CORS_ORIGINS
from expense_validator.app.classifiers import SHADOW_CAP_USD, build_classifier, sync_prompt_links
from expense_validator.app.intake import default_classifier
from expense_validator.app.reviewing import ReviewService
from expense_validator.app.service import ReceiptService
from expense_validator.app.worker import Worker
from expense_validator.paths import CLASSIFICATIONS_FILE, DEFAULT_DB_FILE
from expense_validator.ports.classifier import ItemClassifier


def db_path(explicit: str | None = None, env: Mapping[str, str] | None = None) -> Path:
    """The database file: the flag, else `EPV_DB`, else `var/epv.sqlite3`."""
    env = os.environ if env is None else env
    chosen = explicit or env.get("EPV_DB")
    return Path(chosen) if chosen else DEFAULT_DB_FILE


def cors_origins(
    explicit: Sequence[str] | None = None, env: Mapping[str, str] | None = None
) -> list[str]:
    """The origins allowed to call the API from a browser: the flags, else `EPV_CORS_ORIGINS`
    (comma separated), else the local front end's."""
    env = os.environ if env is None else env
    if explicit:
        return list(explicit)
    listed = env.get("EPV_CORS_ORIGINS", "")
    chosen = [origin.strip() for origin in listed.split(",") if origin.strip()]
    return chosen or list(DEFAULT_CORS_ORIGINS)


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
    seed_path: Path = CLASSIFICATIONS_FILE,
    cap_usd: float = CAP_USD,
    classifier: str = "openrouter",
    simulated_latency_ms: int = 0,
    shadow: str | None = None,
    shadow_cap_usd: float = SHADOW_CAP_USD,
) -> Worker:
    """The worker with the configured classifier over the database's answer table.

    The table is seeded from `seed_path` (the committed answers) when it is empty, so the
    application never changes committed outputs, and each billed answer is durable as soon as it
    is stored, so a crash costs nothing on resume and several workers share the answers.
    Langfuse is best effort: with no keys or no server the worker runs untraced.

    `classifier` is `openrouter` (the default), `keyword` or `simulated`; the last two make no model
    call and are for baselines and load tests. `simulated_latency_ms` adds a sleep per line to any
    of them, to reproduce a model's latency without paying for it.

    `shadow` names a second classifier (`jev-1.13` or `jev-hybrid`) whose answers are stored beside
    the deciding one's and decide nothing. It is built through the same factory over the same
    answer table, with its own counters and its own cap, `shadow_cap_usd`. Off by default.
    """
    tracer = make_tracer(disabled=no_trace)
    config = load_pipeline_config()
    chosen: ItemClassifier
    if classifier == "openrouter":
        links = sync_prompt_links(config.classifier_model, tracer, offline)
        cache = SqliteClassificationCache(store.path, utc_now)
        cache.seed_from(seed_path)
        chosen = default_classifier(
            tracer, cache, offline=offline, prompt_links=links, cap_usd=cap_usd
        )
    elif classifier == "keyword":
        chosen = KeywordClassifier()
    elif classifier == "simulated":
        chosen = SimulatedClassifier()
    else:
        raise ValueError(f"unknown classifier: {classifier!r}")
    if simulated_latency_ms > 0:
        chosen = LatencyClassifier(chosen, simulated_latency_ms)
    shadow_classifier: ItemClassifier | None = None
    if shadow:
        shadow_classifier = build_classifier(
            shadow,
            tracer,
            SqliteClassificationCache(store.path, utc_now),
            offline=offline,
            prompt_links=sync_prompt_links(shadow, tracer, offline),
            null_subtype_as_none=config.null_subtype_as_none,
            cap_usd=shadow_cap_usd,
        )
    return Worker(
        store,
        chosen,
        tracer,
        load_settings(),
        utc_now,
        config,
        shadow=shadow_classifier,
        shadow_name=shadow,
    )
