"""The answer cache behind its port: the JSONL adapter and the table adapter (spec 006, US1)."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable
from contextlib import closing
from pathlib import Path

import pytest

from expense_validator.adapters.classification_cache import ClassificationCache
from expense_validator.adapters.sqlite_cache import SqliteClassificationCache
from expense_validator.adapters.sqlite_store import SqliteStore
from expense_validator.domain.models import CacheEntry
from expense_validator.paths import CLASSIFICATIONS_FILE
from expense_validator.ports.classification_cache import ClassificationCachePort
from tests.fakes import StepClock
from tests.unit.test_cache import entry

Factory = Callable[[Path], ClassificationCachePort]


def jsonl(directory: Path) -> ClassificationCachePort:
    return ClassificationCache(directory / "cache.jsonl")


def table(directory: Path) -> ClassificationCachePort:
    store = SqliteStore(directory / "epv.sqlite3")
    return SqliteClassificationCache(store.path, StepClock())


@pytest.fixture(params=[jsonl, table], ids=["jsonl", "table"])
def cache(request: pytest.FixtureRequest, tmp_path: Path) -> ClassificationCachePort:
    factory: Factory = request.param
    return factory(tmp_path)


def other(key: str) -> CacheEntry:
    return entry(key).model_copy(update={"content": "another answer", "request_id": "gen-2"})


# The port contract, over both adapters


def test_a_missing_key_is_none(cache: ClassificationCachePort) -> None:
    assert cache.get("a" * 64) is None
    assert len(cache) == 0


def test_put_says_whether_it_stored_the_row_and_keeps_the_first(
    cache: ClassificationCachePort,
) -> None:
    key = "a" * 64
    assert cache.put(entry(key)) is True
    assert cache.put(other(key)) is False
    assert cache.get(key) == entry(key)  # the first answer stays


def test_len_counts_rows(cache: ClassificationCachePort) -> None:
    for letter in "abc":
        cache.put(entry(letter * 64))
    cache.put(other("a" * 64))
    assert len(cache) == 3


# The table adapter only


@pytest.fixture
def db(tmp_path: Path) -> Path:
    return SqliteStore(tmp_path / "epv.sqlite3").path


def test_seeding_inserts_the_committed_rows_once(db: Path) -> None:
    cache = SqliteClassificationCache(db, StepClock())
    assert cache.seed_from(CLASSIFICATIONS_FILE) == 78
    assert len(cache) == 78
    assert cache.seed_from(CLASSIFICATIONS_FILE) == 0  # a non-empty table is left alone
    with closing(sqlite3.connect(db)) as conn:
        assert (
            conn.execute("SELECT COUNT(*) FROM classification_cache WHERE seeded = 1").fetchone()[0]
            == 78
        )


def test_the_export_is_the_committed_file_byte_for_byte(db: Path) -> None:
    cache = SqliteClassificationCache(db, StepClock())
    cache.seed_from(CLASSIFICATIONS_FILE)
    exported = "".join(line + "\n" for line in cache.export_lines())
    assert exported.encode("utf-8") == CLASSIFICATIONS_FILE.read_bytes()


def test_rows_added_later_are_exported_in_key_order_and_not_marked_seeded(db: Path) -> None:
    cache = SqliteClassificationCache(db, StepClock())
    cache.put(entry("b" * 64))
    cache.put(entry("a" * 64))
    assert [json.loads(line)["cache_key"][0] for line in cache.export_lines()] == ["a", "b"]
    with closing(sqlite3.connect(db)) as conn:
        assert conn.execute("SELECT seeded FROM classification_cache").fetchall() == [(0,), (0,)]
        model, prompt, cost = conn.execute(
            "SELECT model_id, prompt_version, cost_usd FROM classification_cache LIMIT 1"
        ).fetchone()
    assert (model, prompt, cost) == ("m", "p", 0.0001)


def test_two_instances_on_one_file_see_each_others_rows_at_once(db: Path) -> None:
    first = SqliteClassificationCache(db, StepClock())
    second = SqliteClassificationCache(db, StepClock())
    key = "c" * 64
    assert first.put(entry(key)) is True
    assert second.get(key) == entry(key)
    assert second.put(other(key)) is False
    assert first.get(key) == entry(key)
    assert len(first) == len(second) == 1
