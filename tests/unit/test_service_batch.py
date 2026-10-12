"""Batches: partial success, per-row outcomes, a summary by state (FR-007, FR-008, ADR 0006)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from expense_validator.app.batching import MAX_ROWS, BatchService
from expense_validator.app.errors import InvalidBatchError, NotFoundError
from tests.support import Stack, build_stack, notebook_classifier, receipt_json


@pytest.fixture
def stack(tmp_path: Path) -> Stack:
    return build_stack(tmp_path)


@pytest.fixture
def batches(stack: Stack) -> BatchService:
    return BatchService(stack.service)


def jsonl(*rows: str) -> str:
    return "\n".join(rows) + "\n"


def outcomes(view) -> list[tuple[int, str | None, str]]:  # type: ignore[no-untyped-def]
    return [(i.row, i.receipt_id, i.outcome) for i in view.items]


def test_a_clean_batch_is_accepted_row_by_row(batches: BatchService) -> None:
    view = batches.submit(jsonl(receipt_json("SYN-1"), receipt_json("SYN-2")))
    assert view.batch_id.startswith("bat_") and view.total == 2
    assert outcomes(view) == [(1, "SYN-1", "accepted"), (2, "SYN-2", "accepted")]
    assert view.counts == {"submitted": 2} and view.has_problems is False


def test_bad_rows_are_reported_with_their_number_and_the_good_ones_proceed(
    stack: Stack, batches: BatchService
) -> None:
    text = jsonl(
        receipt_json("SYN-1"), "{not json", "42", '{"receipt_id": "X"}', receipt_json("SYN-2")
    )
    view = batches.submit(text)
    assert outcomes(view) == [
        (1, "SYN-1", "accepted"),
        (2, None, "invalid"),
        (3, None, "invalid"),
        (4, None, "invalid"),
        (5, "SYN-2", "accepted"),
    ]
    errors = {i.row: i.error for i in view.items if i.error}
    assert "not valid JSON" in errors[2] and "JSON object" in errors[3]
    assert "employee_id" in errors[4]
    assert view.has_problems is True
    assert view.counts == {"invalid": 3, "submitted": 2}
    assert stack.service.list_receipts()[1] == 2  # only the good rows were stored


def test_the_same_receipt_twice_in_one_batch_is_a_duplicate_within_the_batch(
    batches: BatchService,
) -> None:
    view = batches.submit(jsonl(receipt_json("SYN-1"), receipt_json("SYN-1", amount="99.00")))
    assert outcomes(view) == [(1, "SYN-1", "accepted"), (2, "SYN-1", "duplicate_in_batch")]
    assert "duplicate" in (view.items[1].error or "")
    assert view.counts == {"duplicate_in_batch": 1, "submitted": 1}  # the receipt counts once


def test_submitting_the_same_batch_again_creates_nothing_new(
    stack: Stack, batches: BatchService
) -> None:
    text = jsonl(receipt_json("SYN-1"), receipt_json("SYN-2"))
    first = batches.submit(text)
    again = batches.submit(text)
    assert again.batch_id != first.batch_id  # a new submission, with its own record
    assert [i.outcome for i in again.items] == ["existing", "existing"]
    with stack.store.transaction(write=False) as tx:
        assert tx.open_work_count() == 2  # no new work
        assert len(tx.list_revisions("SYN-1")) == 1


def test_a_changed_receipt_in_a_later_batch_is_a_revision(batches: BatchService) -> None:
    batches.submit(jsonl(receipt_json("SYN-1")))
    view = batches.submit(jsonl(receipt_json("SYN-1", amount="99.00")))
    assert [i.outcome for i in view.items] == ["revision"]


def test_a_json_array_is_accepted_like_jsonl(batches: BatchService) -> None:
    rows = [json.loads(receipt_json("SYN-1")), json.loads(receipt_json("SYN-2"))]
    view = batches.submit(json.dumps(rows))
    assert [i.outcome for i in view.items] == ["accepted", "accepted"]


def test_the_summary_follows_the_receipts_as_they_are_processed(
    stack: Stack, batches: BatchService
) -> None:
    view = batches.submit(jsonl(receipt_json("SYN-1"), receipt_json("SYN-2")))
    stack.worker(notebook_classifier()).run_once()
    later = batches.get(view.batch_id)
    assert later.counts == {"auto_approved": 2}
    assert {i.state for i in later.items} == {"auto_approved"}


def test_a_failed_item_shows_in_the_summary_and_can_be_retried_alone(
    stack: Stack, batches: BatchService
) -> None:
    view = batches.submit(jsonl(receipt_json("SYN-1"), receipt_json("SYN-2")))
    stack.worker(notebook_classifier(fail_with=RuntimeError("down"))).run_once()
    assert batches.get(view.batch_id).counts == {"failed": 2}
    stack.service.retry("SYN-1")
    stack.worker(notebook_classifier()).run_once()
    assert batches.get(view.batch_id).counts == {"auto_approved": 1, "failed": 1}


def test_receipts_can_be_listed_by_batch(stack: Stack, batches: BatchService) -> None:
    stack.service.submit(receipt_json("SYN-0"))
    view = batches.submit(jsonl(receipt_json("SYN-1"), receipt_json("SYN-2")))
    records, total = stack.service.list_receipts(batch_id=view.batch_id)
    assert (total, [r.receipt_id for r in records]) == (2, ["SYN-1", "SYN-2"])


def test_an_empty_or_oversized_batch_is_refused_and_stores_nothing(
    stack: Stack, batches: BatchService
) -> None:
    with pytest.raises(InvalidBatchError, match="no receipts"):
        batches.submit("  \n ")
    big = jsonl(*[receipt_json(f"SYN-{n}") for n in range(MAX_ROWS + 1)])
    with pytest.raises(InvalidBatchError, match=str(MAX_ROWS)):
        batches.submit(big)
    assert stack.service.list_receipts()[1] == 0


def test_an_unknown_batch_is_not_found(batches: BatchService) -> None:
    with pytest.raises(NotFoundError):
        batches.get("bat_nope")


def test_answer_keys_in_a_batch_are_stripped_like_anywhere_else(
    stack: Stack, batches: BatchService
) -> None:
    from tests.support import FIXTURE

    batches.submit(jsonl(FIXTURE.read_text(encoding="utf-8").strip()))
    with stack.store.transaction(write=False) as tx:
        stored = tx.get_revision("SYN-FIREWALL", 1)
    assert stored is not None and "labels" not in stored.receipt.model_dump_json()
