"""Cross-receipt re-evaluation: the result does not depend on arrival order (ADR 0007 D6, D7).

Two meals for one employee-day break MEAL-01 only together (40 + 50 > 75, domestic cap).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from expense_validator.adapters.config_files import load_settings
from expense_validator.adapters.tracing import NoopTracer
from expense_validator.app.pipeline import run_pipeline
from expense_validator.app.service import parse_receipt
from expense_validator.domain.events import NoticeRaised, ReceiptEvaluated
from expense_validator.domain.models import ReceiptResult
from tests.fakes import BillingClassifier
from tests.support import Stack, build_stack, receipt_json

MEAL = {"submitted_expense_type": "Meals - Individual"}
CATEGORIES = {"Lunch A": "food_beverage", "Lunch B": "food_beverage", "Pens": "office_supplies"}


def lunch(rid: str, amount: str, description: str, **overrides: object) -> str:
    return receipt_json(rid, amount, description, **MEAL, **overrides)


def classifier() -> BillingClassifier:
    return BillingClassifier(dict(CATEGORIES))


def batch_results(*texts: str) -> dict[str, ReceiptResult]:
    receipts = [parse_receipt(t) for t in texts]
    results = run_pipeline(receipts, classifier(), NoopTracer(), load_settings(), "t")
    return {r.receipt_id: r for r in results}


def rule_ids(stack: Stack, receipt_id: str) -> set[str]:
    result = stack.service.get_receipt(receipt_id).result
    assert result is not None
    return {e.rule_id for e in result.exceptions}


def versions(stack: Stack, receipt_id: str) -> int:
    view = stack.service.get_receipt(receipt_id)
    with stack.store.transaction(write=False) as tx:
        return len(tx.list_evaluations(receipt_id, view.record.current_revision))


@pytest.fixture
def stack(tmp_path: Path) -> Stack:
    return build_stack(tmp_path)


@pytest.mark.parametrize("first", ["A", "B"])
def test_the_second_meal_re_evaluates_the_first_in_either_order(stack: Stack, first: str) -> None:
    a, b = lunch("SYN-A", "40", "Lunch A"), lunch("SYN-B", "50", "Lunch B")
    one, two = (a, b) if first == "A" else (b, a)
    worker = stack.worker(classifier())

    stack.service.submit(one)
    worker.run_once()
    assert "MEAL-01" not in rule_ids(stack, parse_receipt(one).receipt_id)

    stack.service.submit(two)
    worker.run_once()
    for rid in ("SYN-A", "SYN-B"):
        assert "MEAL-01" in rule_ids(stack, rid)
    assert versions(stack, parse_receipt(one).receipt_id) == 2  # the first gained a version
    assert versions(stack, parse_receipt(two).receipt_id) == 1


@pytest.mark.parametrize("order", [("A", "B"), ("B", "A")])
@pytest.mark.parametrize("drain_between", [True, False])
def test_the_final_results_equal_the_batch_run(
    stack: Stack, order: tuple[str, str], drain_between: bool
) -> None:
    texts = {"A": lunch("SYN-A", "40", "Lunch A"), "B": lunch("SYN-B", "50", "Lunch B")}
    worker = stack.worker(classifier())
    for key in order:
        stack.service.submit(texts[key])
        if drain_between:
            worker.run_once()
    worker.run_once()
    expected = batch_results(*texts.values())
    for rid in ("SYN-A", "SYN-B"):
        assert stack.service.get_receipt(rid).result == expected[rid]


def test_receipts_submitted_together_are_evaluated_once_with_the_full_context(
    stack: Stack,
) -> None:
    stack.service.submit(lunch("SYN-A", "40", "Lunch A"))
    stack.service.submit(lunch("SYN-B", "50", "Lunch B"))
    stack.worker(classifier()).run_once()
    assert versions(stack, "SYN-A") == versions(stack, "SYN-B") == 1
    assert "MEAL-01" in rule_ids(stack, "SYN-A")


def test_an_unrelated_receipt_is_not_touched_by_the_cascade(stack: Stack) -> None:
    stack.service.submit(receipt_json("SYN-U", "12.50", "Pens", employee_id="E-OTHER"))
    worker = stack.worker(classifier())
    worker.run_once()
    stack.service.submit(lunch("SYN-A", "40", "Lunch A"))
    stack.service.submit(lunch("SYN-B", "50", "Lunch B"))
    worker.run_once()
    assert versions(stack, "SYN-U") == 1
    with stack.store.transaction(write=False) as tx:
        evaluations = [e for e in tx.list_events("SYN-U") if isinstance(e.event, ReceiptEvaluated)]
    assert len(evaluations) == 1


def test_an_auto_approved_receipt_that_now_needs_review_returns_to_the_queue_with_a_notice(
    stack: Stack,
) -> None:
    worker = stack.worker(classifier())
    stack.service.submit(lunch("SYN-A", "40", "Lunch A"))
    worker.run_once()
    assert stack.service.get_receipt("SYN-A").record.state == "auto_approved"
    stack.service.submit(lunch("SYN-B", "50", "Lunch B"))
    worker.run_once()
    view = stack.service.get_receipt("SYN-A")
    assert view.record.state == "in_review" and view.record.disposition == "flag"
    assert view.record.notice is not None and "re-evaluation" in view.record.notice
    with stack.store.transaction(write=False) as tx:
        assert any(isinstance(e.event, NoticeRaised) for e in tx.list_events("SYN-A"))


def test_an_untouched_receipt_in_the_queue_updates_its_proposal_without_a_notice(
    stack: Stack,
) -> None:
    worker = stack.worker(classifier())
    stack.service.submit(lunch("SYN-A", "40", "Lunch A", merchant_name=None))
    stack.service.submit(lunch("SYN-B", "50", "Lunch B"))
    worker.run_once()
    assert stack.service.get_receipt("SYN-A").record.state == "in_review"
    stack.service.submit(lunch("SYN-B", "10", "Lunch B"))  # B shrinks: the day is fine again
    worker.run_once()
    view = stack.service.get_receipt("SYN-A")
    assert "MEAL-01" not in rule_ids(stack, "SYN-A")
    assert view.record.notice is None


def test_a_revision_that_moves_to_another_day_refreshes_the_group_it_left(stack: Stack) -> None:
    worker = stack.worker(classifier())
    stack.service.submit(lunch("SYN-A", "40", "Lunch A"))
    stack.service.submit(lunch("SYN-B", "50", "Lunch B"))
    worker.run_once()
    assert "MEAL-01" in rule_ids(stack, "SYN-A")

    moved = lunch("SYN-B", "50", "Lunch B", transaction_datetime="2026-05-02T12:00:00")
    stack.service.submit(moved)
    worker.run_once()

    assert "MEAL-01" not in rule_ids(stack, "SYN-A")  # A's day no longer has B in it
    assert "MEAL-01" not in rule_ids(stack, "SYN-B")
    assert stack.service.get_receipt("SYN-B").record.current_revision == 2


def test_a_receipt_with_no_date_or_trip_cascades_to_nobody(stack: Stack) -> None:
    worker = stack.worker(classifier())
    stack.service.submit(lunch("SYN-A", "40", "Lunch A"))
    worker.run_once()
    stack.service.submit(lunch("SYN-N", "50", "Lunch B", transaction_datetime=None))
    worker.run_once()
    assert versions(stack, "SYN-A") == 1
