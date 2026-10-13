"""With shadow on, the 32 receipts still give the results of `epv run` byte for byte (SC-001).

The deciding classifier is the committed cache, offline (no billed call). The shadow is the jev
decision classifier over a fake transport, on the same answer table. Every line gets a shadow row,
and the shadow changes nothing the receipts show: the same results, states and events.
"""

from __future__ import annotations

import json
import random
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any

from expense_validator.adapters.config_files import load_pipeline_config
from expense_validator.adapters.openrouter.decision_classifier import DecisionClassifier
from expense_validator.adapters.receipts_file import load_receipts
from expense_validator.adapters.sqlite_cache import SqliteClassificationCache
from expense_validator.adapters.sqlite_store import SqliteStore, utc_now
from expense_validator.adapters.tracing import NoopTracer
from expense_validator.app.composition import build_service
from expense_validator.paths import RESULTS_FILE
from tests.integration.test_api_parity import offline_classifier, written_results
from tests.support import build_stack


class FakeJev:
    """A decisions endpoint that always says food_beverage and bills a little."""

    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, payload: dict[str, Any]) -> tuple[dict[str, Any], str]:
        self.calls += 1
        body = {
            "id": f"jev-{self.calls}",
            "provider": "typesafe",
            "answers": {
                "category": {
                    "choice": "food_beverage",
                    "probabilities": {"food_beverage": 0.9},
                }
            },
            "usage": {"input_tokens": 700, "output_tokens": 10, "cost": 0.00001},
        }
        return body, json.dumps(body)


def test_the_dataset_with_the_shadow_on_equals_the_batch_run(tmp_path: Path) -> None:
    receipts = load_receipts()
    random.Random(11).shuffle(receipts)
    stack = build_stack(tmp_path)
    primary = offline_classifier(tmp_path)
    transport = FakeJev()
    shadow = DecisionClassifier(
        SqliteClassificationCache(stack.store.path, utc_now),
        NoopTracer(),
        transport=transport,
        raw_dir=tmp_path / "raw",
    )
    worker = stack.worker(
        primary, config=load_pipeline_config(), shadow=shadow, shadow_name="jev-1.13"
    )
    for r in receipts:
        stack.service.submit(r.model_dump_json())
    worker.run_once()

    assert primary.calls_made == 0  # zero billed primary calls
    assert written_results(stack.service, receipts, tmp_path / "out.jsonl") == (
        RESULTS_FILE.read_bytes()
    )
    lines = sum(len(r.line_items) for r in receipts)
    with stack.store.transaction(write=False) as tx:
        rows = list(tx.iter_shadow("jev-1.13"))
    assert len(rows) == lines
    assert {(r.receipt_id, r.line_id) for r in rows} == {
        (r.receipt_id, line.line_id) for r in receipts for line in r.line_items
    }
    assert all(r.classification.status == "classified" for r in rows)
    assert shadow.calls_made == transport.calls  # the shadow's own counters
    assert 0 < transport.calls <= lines  # repeated line texts are answered from the table
    with closing(sqlite3.connect(stack.store.path)) as conn:
        pending = conn.execute(
            "SELECT COUNT(*) FROM outbox WHERE state IN ('pending', 'claimed')"
        ).fetchone()[0]
    assert pending == 0


def test_the_shadow_leaves_every_receipt_as_it_is_without_it(tmp_path: Path) -> None:
    receipts = load_receipts()
    off = build_stack(tmp_path / "off")
    on = build_stack(tmp_path / "on")
    off_worker = off.worker(offline_classifier(tmp_path / "off"), config=load_pipeline_config())
    shadow = DecisionClassifier(
        SqliteClassificationCache(on.store.path, utc_now),
        NoopTracer(),
        transport=FakeJev(),
        raw_dir=tmp_path / "raw",
    )
    on_worker = on.worker(
        offline_classifier(tmp_path / "on"),
        config=load_pipeline_config(),
        shadow=shadow,
        shadow_name="jev-1.13",
    )
    for r in receipts:
        off.service.submit(r.model_dump_json())
        on.service.submit(r.model_dump_json())
    off_worker.run_once()
    on_worker.run_once()
    for r in receipts:
        a, b = off.service.get_receipt(r.receipt_id), on.service.get_receipt(r.receipt_id)
        assert (a.record.state, a.record.disposition, a.record.evaluation_version) == (
            b.record.state,
            b.record.disposition,
            b.record.evaluation_version,
        )
        assert a.result == b.result
    for stack in (off, on):
        with stack.store.transaction(write=False) as tx:
            kinds = [e.event.type for r in receipts for e in tx.list_events(r.receipt_id)]
        assert "StageFailed" not in kinds


def test_the_wiring_that_ships_builds_the_shadow_only_when_asked(tmp_path: Path) -> None:
    from expense_validator.app.composition import build_worker

    store = SqliteStore(tmp_path / "epv.sqlite3")
    assert build_service(store) is not None
    off = build_worker(store, offline=True, no_trace=True)
    assert off.shadow is None
    on = build_worker(store, offline=True, no_trace=True, shadow="jev-hybrid", shadow_cap_usd=0.05)
    assert on.shadow is not None and on.shadow_name == "jev-hybrid"
    assert on.shadow is not on.classifier
    assert getattr(on.shadow.category_source, "cap_usd", None) == 0.05  # type: ignore[attr-defined]
    assert getattr(on.shadow.detail_source, "cap_usd", None) == 0.05  # type: ignore[attr-defined]
    assert getattr(on.classifier, "cap_usd", None) == 1.0  # the primary's cap is its own
