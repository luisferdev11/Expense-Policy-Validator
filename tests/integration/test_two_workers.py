"""Two workers share one database and one answer table (spec 006, SC-001 and SC-002).

(a) Offline, over the 32 receipts: two `Worker` instances interleave `process_next()` on one
database whose cache table is seeded from the committed file. No call is billed and the latest
results equal `outputs/results.jsonl` byte for byte.

(b) Two classifiers over one table, each with its own counting transport, over 20 synthetic
receipts that share 10 distinct new lines: 10 calls in total and 10 new rows. Nothing is billed:
the transport is a fake.
"""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any

from expense_validator.adapters.config_files import load_pipeline_config, load_settings
from expense_validator.adapters.openrouter.classifier import OpenRouterClassifier
from expense_validator.adapters.openrouter.models import PINS
from expense_validator.adapters.receipts_file import load_receipts
from expense_validator.adapters.sqlite_cache import SqliteClassificationCache
from expense_validator.adapters.sqlite_store import SqliteStore, utc_now
from expense_validator.adapters.tracing import NoopTracer
from expense_validator.app.composition import build_service
from expense_validator.app.pipeline import classify_receipt
from expense_validator.app.worker import Worker
from expense_validator.paths import CLASSIFICATIONS_FILE, RESULTS_FILE
from tests.factories import item, receipt
from tests.integration.test_api_parity import written_results


def table_classifier(
    path: Path, transport: Any = None, offline: bool = False, raw_dir: Path | None = None
) -> OpenRouterClassifier:
    config = load_pipeline_config()
    options: dict[str, Any] = {} if raw_dir is None else {"raw_dir": raw_dir}
    return OpenRouterClassifier(
        SqliteClassificationCache(path, utc_now),
        NoopTracer(),
        transport=transport,
        offline=offline,
        pin=PINS[config.classifier_model],
        null_subtype_as_none=config.null_subtype_as_none,
        **options,
    )


def test_two_workers_reproduce_the_batch_run_with_no_billed_call(tmp_path: Path) -> None:
    store = SqliteStore(tmp_path / "epv.sqlite3")
    SqliteClassificationCache(store.path, utc_now).seed_from(CLASSIFICATIONS_FILE)
    config = load_pipeline_config()
    classifiers = [table_classifier(store.path, offline=True) for _ in range(2)]
    workers = [
        Worker(store, clf, NoopTracer(), load_settings(), utc_now, config) for clf in classifiers
    ]
    service = build_service(store)
    receipts = load_receipts()
    random.Random(11).shuffle(receipts)
    for r in receipts:
        service.submit(r.model_dump_json())

    while True:  # the two workers take turns, one item each
        took = [worker.process_next() for worker in workers]
        if not any(took):
            break

    assert [c.calls_made for c in classifiers] == [0, 0]
    assert sum(c.cache_hits for c in classifiers) > 0
    assert written_results(service, receipts, tmp_path / "out.jsonl") == RESULTS_FILE.read_bytes()


class CountingTransport:
    """A fake OpenRouter that answers every request and counts the calls, shared by both sides."""

    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, payload: dict[str, Any]) -> tuple[dict[str, Any], str]:
        self.calls += 1
        answer = {
            "category": "office_supplies",
            "confidence": 0.9,
            "subtype": "none",
            "recipient_kind": "none",
            "recipient_name": None,
        }
        body = {
            "id": f"gen-{self.calls}",
            "provider": "Fake",
            "choices": [{"message": {"content": json.dumps(answer)}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "cost": 0.0001},
        }
        return body, json.dumps(body)


def test_two_classifiers_over_one_table_call_the_model_once_per_distinct_line(
    tmp_path: Path,
) -> None:
    path = SqliteStore(tmp_path / "epv.sqlite3").path
    transport = CountingTransport()
    sides = [table_classifier(path, transport, raw_dir=tmp_path / f"raw-{n}") for n in range(2)]
    for n in range(20):
        r = receipt([item(1, f"SYN-{n}", f"Synthetic line {n % 10}")], receipt_id=f"SYN-{n}")
        classify_receipt(r, sides[n % 2], NoopTracer(), "test")

    assert transport.calls == 10
    assert sum(side.calls_made for side in sides) == 10
    assert len(SqliteClassificationCache(path, utc_now)) == 10
