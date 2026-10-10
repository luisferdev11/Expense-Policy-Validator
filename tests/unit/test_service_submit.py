"""Submitting receipts: persist first, idempotent, revisions (ADR 0006, ADR 0007 D4 and D5)."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from expense_validator.adapters.sqlite_store import SqliteStore
from expense_validator.app.errors import (
    IdempotencyKeyReuseError,
    InvalidIdempotencyKeyError,
    InvalidReceiptError,
)
from expense_validator.app.service import ReceiptService
from expense_validator.domain.events import ReceiptSubmitted, RevisionSuperseded
from tests.fakes import StepClock
from tests.support import FIXTURE
from tests.support import receipt_json as raw


@pytest.fixture
def store(tmp_path: Path) -> SqliteStore:
    return SqliteStore(tmp_path / "epv.sqlite3")


@pytest.fixture
def service(store: SqliteStore) -> ReceiptService:
    return ReceiptService(store, StepClock())


def test_a_new_receipt_is_stored_before_any_work_and_queued(
    service: ReceiptService, store: SqliteStore
) -> None:
    outcome = service.submit(raw())
    assert (outcome.outcome, outcome.revision, outcome.state) == ("accepted", 1, "submitted")
    with store.transaction(write=False) as tx:
        assert tx.get_receipt("SYN-1") is not None
        events = tx.list_events("SYN-1")
        assert [type(e.event) for e in events] == [ReceiptSubmitted]
        assert tx.open_work_count() == 1


def test_the_same_receipt_twice_is_one_receipt_and_one_processing(
    service: ReceiptService, store: SqliteStore
) -> None:
    first = service.submit(raw())
    again = service.submit(raw())
    assert again.outcome == "existing" and again.revision == first.revision == 1
    with store.transaction(write=False) as tx:
        assert len(tx.list_revisions("SYN-1")) == 1
        assert len(tx.list_events("SYN-1")) == 1
        assert tx.open_work_count() == 1


def test_a_decimal_written_another_way_is_the_same_receipt(service: ReceiptService) -> None:
    service.submit(raw(amount="12.50"))
    assert service.submit(raw(amount="12.5")).outcome == "existing"


def test_the_same_content_under_a_new_client_key_is_existing_and_remembers_the_key(
    service: ReceiptService, store: SqliteStore
) -> None:
    service.submit(raw(), client_key="first")
    again = service.submit(raw(), client_key="second")
    assert again.outcome == "existing"
    with store.transaction(write=False) as tx:
        assert tx.get_submission("second") is not None
        assert len(tx.list_revisions("SYN-1")) == 1


def test_a_client_key_reused_with_another_body_is_rejected_and_changes_nothing(
    service: ReceiptService, store: SqliteStore
) -> None:
    service.submit(raw(), client_key="k1")
    with pytest.raises(IdempotencyKeyReuseError):
        service.submit(raw(amount="99.00"), client_key="k1")
    with store.transaction(write=False) as tx:
        assert len(tx.list_revisions("SYN-1")) == 1


def test_a_changed_receipt_without_a_key_is_the_next_revision(
    service: ReceiptService, store: SqliteStore
) -> None:
    service.submit(raw())
    second = service.submit(raw(amount="99.00"))
    assert (second.outcome, second.revision, second.state) == ("revision", 2, "submitted")
    with store.transaction(write=False) as tx:
        revisions = tx.list_revisions("SYN-1")
        assert [(r.revision, r.status) for r in revisions] == [(1, "superseded"), (2, "current")]
        record = tx.get_receipt("SYN-1")
        assert record is not None and record.current_revision == 2
        kinds = [type(e.event) for e in tx.list_events("SYN-1")]
        assert kinds == [ReceiptSubmitted, RevisionSuperseded, ReceiptSubmitted]
        assert tx.open_work_count() == 1  # the old revision's work was cancelled


def test_going_back_to_an_earlier_content_is_a_new_revision_not_an_echo(
    service: ReceiptService,
) -> None:
    service.submit(raw())
    service.submit(raw(amount="99.00"))
    third = service.submit(raw())
    assert (third.outcome, third.revision) == ("revision", 3)
    assert service.submit(raw()).outcome == "existing"


def test_a_superseded_submission_retried_with_its_key_is_existing_and_says_so(
    service: ReceiptService,
) -> None:
    service.submit(raw(), client_key="k1")
    service.submit(raw(amount="99.00"))
    again = service.submit(raw(), client_key="k1")
    assert again.outcome == "existing" and again.superseded is True
    assert again.revision == 2  # the receipt's current revision


def test_answer_keys_are_discarded_and_never_stored(
    service: ReceiptService, store: SqliteStore
) -> None:
    service.submit(FIXTURE.read_text(encoding="utf-8"))
    with store.transaction(write=False) as tx:
        content = tx.get_revision("SYN-FIREWALL", 1)
        assert content is not None
        dumped = content.receipt.model_dump_json()
    for key in ("labels", "notes", "expected_exceptions"):
        assert key not in dumped
    with store.transaction(write=False) as tx:
        events = tx.list_events("SYN-FIREWALL")
    assert all("labels" not in e.event.model_dump_json() for e in events)


def test_a_receipt_with_and_without_answer_keys_is_the_same_receipt(
    service: ReceiptService,
) -> None:
    text = FIXTURE.read_text(encoding="utf-8")
    service.submit(text)
    stripped = json.loads(text)
    for key in ("labels", "notes"):
        stripped.pop(key)
    for line in stripped["line_items"]:
        line.pop("labels")
    assert service.submit(json.dumps(stripped)).outcome == "existing"


def test_money_keeps_its_decimal_precision(service: ReceiptService, store: SqliteStore) -> None:
    service.submit(raw(amount="0.1"))
    with store.transaction(write=False) as tx:
        found = tx.get_revision("SYN-1", 1)
    assert found is not None and found.receipt.total_amount == Decimal("0.1")


@pytest.mark.parametrize(
    ("body", "fragment"),
    [
        ("", "not valid JSON"),
        ("{not json", "not valid JSON"),
        ("[1, 2]", "JSON object"),
        ("42", "JSON object"),
        ('{"receipt_id": "X"}', "employee_id"),
    ],
)
def test_malformed_input_is_rejected_with_the_problem_named_and_nothing_stored(
    service: ReceiptService, store: SqliteStore, body: str, fragment: str
) -> None:
    with pytest.raises(InvalidReceiptError, match=fragment):
        service.submit(body)
    with store.transaction(write=False) as tx:
        assert tx.list_receipts()[1] == 0 and tx.open_work_count() == 0


def test_an_empty_or_overlong_client_key_is_rejected(service: ReceiptService) -> None:
    with pytest.raises(InvalidIdempotencyKeyError):
        service.submit(raw(), client_key="  ")
    with pytest.raises(InvalidIdempotencyKeyError):
        service.submit(raw(), client_key="k" * 300)


def test_simultaneous_submissions_of_one_receipt_make_one_receipt(
    store: SqliteStore,
) -> None:
    service = ReceiptService(store, lambda: datetime(2026, 10, 10, tzinfo=UTC))
    with ThreadPoolExecutor(max_workers=8) as pool:
        outcomes = list(pool.map(lambda _: service.submit(raw()), range(8)))
    assert sorted(o.outcome for o in outcomes) == ["accepted"] + ["existing"] * 7
    with store.transaction(write=False) as tx:
        assert len(tx.list_revisions("SYN-1")) == 1
        assert tx.open_work_count() == 1
