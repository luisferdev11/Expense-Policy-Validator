"""A worker that dies mid-batch is resumed without loss, change or extra billed calls (SC-003).

The shared `cache` dict plays the cache file that survives a restart. A crash is a
`SimulatedCrash` (a `BaseException`): no stage handler catches it, so the item stays leased,
exactly as when a process is killed.
"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest

from expense_validator.domain.models import Classification, ReceiptResult
from tests.fakes import BillingClassifier, SimulatedCrash
from tests.support import Stack, build_stack, receipt_json

DESCRIPTIONS = {f"Item {n}": "office_supplies" for n in range(6)}
IDS = [f"SYN-{n}" for n in range(6)]


def submit_all(stack: Stack) -> None:
    for n, rid in enumerate(IDS):
        stack.service.submit(receipt_json(rid, "10.00", f"Item {n}", employee_id=f"E-{n}"))


def results(stack: Stack) -> dict[str, ReceiptResult]:
    out: dict[str, ReceiptResult] = {}
    for rid in IDS:
        result = stack.service.get_receipt(rid).result
        assert result is not None
        out[rid] = result
    return out


@pytest.fixture
def reference(tmp_path: Path) -> tuple[dict[str, ReceiptResult], int]:
    """An uninterrupted run: its results and how many billed calls it made."""
    stack = build_stack(tmp_path / "reference")
    classifier = BillingClassifier(DESCRIPTIONS)
    submit_all(stack)
    stack.worker(classifier).run_once()
    return results(stack), classifier.calls_made


@pytest.mark.parametrize("crash_after", [0, 1, 3, 5])
def test_a_worker_killed_mid_batch_resumes_with_identical_results_and_no_extra_billing(
    tmp_path: Path,
    reference: tuple[dict[str, ReceiptResult], int],
    crash_after: int,
) -> None:
    expected, billed_uninterrupted = reference
    stack = build_stack(tmp_path / "crashed")
    cache: dict[tuple[str, str, int], Classification] = {}
    submit_all(stack)

    first = BillingClassifier(DESCRIPTIONS, cache, crash_after=crash_after)
    with pytest.raises(SimulatedCrash):
        stack.worker(first).run_once()
    stack.clock.advance(timedelta(seconds=61))  # the dead worker's lease runs out

    second = BillingClassifier(DESCRIPTIONS, cache)
    stack.worker(second).run_once()

    assert results(stack) == expected
    assert first.calls_made + second.calls_made == billed_uninterrupted
    for rid in IDS:
        assert stack.service.get_receipt(rid).record.state != "failed"


def test_resuming_never_repeats_a_stage_that_already_committed(tmp_path: Path) -> None:
    stack = build_stack(tmp_path)
    cache: dict[tuple[str, str, int], Classification] = {}
    submit_all(stack)
    with pytest.raises(SimulatedCrash):
        stack.worker(BillingClassifier(DESCRIPTIONS, cache, crash_after=3)).run_once()
    stack.clock.advance(timedelta(seconds=61))
    stack.worker(BillingClassifier(DESCRIPTIONS, cache)).run_once()
    for rid in IDS:
        with stack.store.transaction(write=False) as tx:
            kinds = [e.event.type for e in tx.list_events(rid)]
        assert kinds.count("ReceiptClassified") == 1
        assert kinds.count("ReceiptEvaluated") == 1


@pytest.mark.parametrize("crash_after", [0, 2, 5])
def test_a_shadow_item_interrupted_mid_receipt_resumes_with_no_duplicate_rows(
    tmp_path: Path, crash_after: int
) -> None:
    """A shadow classifier that dies leaves its item leased; once the lease expires another worker
    finishes the work, stores one row per line, and nothing about any receipt is repeated."""
    stack = build_stack(tmp_path)
    submit_all(stack)
    primary = BillingClassifier(DESCRIPTIONS)
    shadow_answers = {description: "tobacco" for description in DESCRIPTIONS}
    shadow_cache: dict[tuple[str, str, int], Classification] = {}

    first = BillingClassifier(shadow_answers, shadow_cache, crash_after=crash_after)
    with pytest.raises(SimulatedCrash):
        stack.worker(primary, shadow=first, shadow_name="jev-1.13").run_once()
    stack.clock.advance(timedelta(seconds=61))
    second = BillingClassifier(shadow_answers, shadow_cache)
    stack.worker(primary, shadow=second, shadow_name="jev-1.13").run_once()

    with stack.store.transaction(write=False) as tx:
        rows = [row for rid in IDS for row in tx.shadow_for(rid, 1)]
    assert len(rows) == len(IDS)  # one row per line, six receipts of one line
    assert len({(r.receipt_id, r.line_id, r.classifier) for r in rows}) == len(IDS)
    assert {r.classification.category for r in rows} == {"tobacco"}
    assert first.calls_made + second.calls_made == len(IDS)  # no shadow answer paid for twice
    for rid in IDS:
        record = stack.service.get_receipt(rid).record
        assert record.state != "failed" and record.failed_stage is None
        with stack.store.transaction(write=False) as tx:
            kinds = [e.event.type for e in tx.list_events(rid)]
        assert kinds.count("ReceiptClassified") == 1 and "StageFailed" not in kinds
