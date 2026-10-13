"""The 32 receipts through the backend give the results of `epv run`, in any order (SC-001, SC-002).

Every receipt enters through the service's stripping path, is classified by the committed cache
(offline, so no model call), and is decided by the shared decision step. The latest evaluation of
each receipt is written with the batch run's own writer and compared byte for byte with
`outputs/results.jsonl`. Receipts are submitted in five shuffled orders, either all at once or
with the worker drained after every submission, which makes the cascade re-evaluate receipts
whose partners arrive later.
"""

from __future__ import annotations

import random
import shutil
from pathlib import Path

import pytest

from expense_validator.adapters.classification_cache import ClassificationCache
from expense_validator.adapters.config_files import load_pipeline_config
from expense_validator.adapters.openrouter.classifier import OpenRouterClassifier
from expense_validator.adapters.openrouter.models import PINS
from expense_validator.adapters.receipts_file import load_receipts
from expense_validator.adapters.results_files import write_results
from expense_validator.adapters.sqlite_cache import SqliteClassificationCache
from expense_validator.adapters.sqlite_store import SqliteStore, utc_now
from expense_validator.adapters.tracing import NoopTracer
from expense_validator.app.composition import build_service, build_worker
from expense_validator.app.service import ReceiptService
from expense_validator.domain.models import ReceiptInput
from expense_validator.paths import CLASSIFICATIONS_FILE, RESULTS_FILE
from tests.support import Stack, build_stack

SEEDS = [0, 1, 2, 3, 4]


def offline_classifier(directory: Path) -> OpenRouterClassifier:
    cache = directory / "cache.jsonl"
    shutil.copy(CLASSIFICATIONS_FILE, cache)
    return OpenRouterClassifier(
        ClassificationCache(cache),
        NoopTracer(),
        offline=True,
        pin=PINS[load_pipeline_config().classifier_model],
    )


def run_in_order(
    directory: Path, receipts: list[ReceiptInput], drain_between: bool
) -> tuple[Stack, OpenRouterClassifier]:
    stack = build_stack(directory)
    classifier = offline_classifier(directory)
    worker = stack.worker(classifier, config=load_pipeline_config())
    for r in receipts:
        stack.service.submit(r.model_dump_json())
        if drain_between:
            worker.run_once()
    worker.run_once()
    return stack, classifier


def written_results(service: ReceiptService, receipts: list[ReceiptInput], out: Path) -> bytes:
    results = []
    for rid in sorted(r.receipt_id for r in receipts):
        found = service.get_receipt(rid).result
        assert found is not None, rid
        results.append(found)
    write_results(out, results)
    return out.read_bytes()


@pytest.mark.parametrize("drain_between", [False, True], ids=["together", "one by one"])
@pytest.mark.parametrize("seed", SEEDS)
def test_the_dataset_through_the_backend_equals_the_batch_run(
    tmp_path: Path, seed: int, drain_between: bool
) -> None:
    receipts = load_receipts()
    assert len(receipts) == 32
    random.Random(seed).shuffle(receipts)

    stack, classifier = run_in_order(tmp_path, receipts, drain_between)

    assert classifier.calls_made == 0  # every answer came from the committed cache
    assert (
        written_results(stack.service, receipts, tmp_path / "out.jsonl")
        == RESULTS_FILE.read_bytes()
    )


def test_the_wiring_that_ships_equals_the_batch_run(tmp_path: Path) -> None:
    """The same proof through the composition root `epv worker` uses: its configured classifier
    (with the config's flags) over the database's answer table, seeded from the committed file.
    Nothing is built by hand here."""
    store = SqliteStore(tmp_path / "epv.sqlite3")
    service = build_service(store)
    committed_before = CLASSIFICATIONS_FILE.read_bytes()
    worker = build_worker(store, offline=True, no_trace=True)
    receipts = load_receipts()
    random.Random(7).shuffle(receipts)
    for r in receipts:
        service.submit(r.model_dump_json())
    worker.run_once()

    assert written_results(service, receipts, tmp_path / "out.jsonl") == RESULTS_FILE.read_bytes()
    assert len(SqliteClassificationCache(store.path, utc_now)) == 78  # seeded from the file
    assert CLASSIFICATIONS_FILE.read_bytes() == committed_before  # which is left untouched


def test_submitting_everything_again_starts_no_new_work(tmp_path: Path) -> None:
    receipts = load_receipts()
    stack, _ = run_in_order(tmp_path, receipts, drain_between=False)
    with stack.store.transaction(write=False) as tx:
        events_before = sum(len(tx.list_events(r.receipt_id)) for r in receipts)

    outcomes = [stack.service.submit(r.model_dump_json()).outcome for r in receipts]

    assert outcomes == ["existing"] * 32
    with stack.store.transaction(write=False) as tx:
        assert tx.open_work_count() == 0
        assert sum(len(tx.list_events(r.receipt_id)) for r in receipts) == events_before
        assert tx.list_receipts()[1] == 32


def test_every_receipt_reaches_a_resting_state(tmp_path: Path) -> None:
    receipts = load_receipts()
    stack, _ = run_in_order(tmp_path, receipts, drain_between=False)
    records, total = stack.service.list_receipts(limit=100)
    assert total == 32
    assert {r.state for r in records} <= {"auto_approved", "in_review", "compliance"}
