"""A re-evaluation that fails must not take a decided receipt out of its state.

A receipt that already has an evaluation keeps its state (approved, in review, ...) when a later
evaluation of it fails; the failure is shown on the receipt and a retry runs it again. Only a
receipt that has never been evaluated is `failed`.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from expense_validator.app import worker as worker_module
from expense_validator.domain.events import NoticeRaised, StageFailed, StageRetried
from tests.support import MEAL, ReviewEnv


@pytest.fixture
def env(tmp_path: Path) -> ReviewEnv:
    e = ReviewEnv(tmp_path)
    e.seed()
    return e


def fail_for(monkeypatch: pytest.MonkeyPatch, receipt_id: str) -> Callable[[], None]:
    """Make the evaluation of one receipt fail until the returned function is called."""
    original = worker_module.build_evaluation

    def failing(tx: Any, settings: Any, meta: Any, rid: str, revision: int) -> Any:
        if rid == receipt_id:
            raise RuntimeError("the store was busy")
        return original(tx, settings, meta, rid, revision)

    monkeypatch.setattr(worker_module, "build_evaluation", failing)
    return lambda: monkeypatch.setattr(worker_module, "build_evaluation", original)


def approve_a_then_shrink_b(env: ReviewEnv) -> None:
    env.act("SYN-A", "approve", reason_code="policy_exception_granted")
    env.submit("SYN-B", "10", "Lunch B", **MEAL)  # B shrinks: A's day is within the cap again


def test_a_failed_re_evaluation_leaves_the_decided_receipt_decided(
    env: ReviewEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    fail_for(monkeypatch, "SYN-A")
    approve_a_then_shrink_b(env)
    env.worker.run_once()

    view = env.service.get_receipt("SYN-A")
    assert view.record.state == "approved"  # the decision does not disappear
    assert view.record.failed_stage == "evaluate"
    assert "RuntimeError" in (view.record.failed_reason or "")
    assert any(isinstance(e, StageFailed) for e in env.events("SYN-A"))


def test_a_retry_runs_the_re_evaluation_again_and_the_receipt_returns_to_review(
    env: ReviewEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    repair = fail_for(monkeypatch, "SYN-A")
    approve_a_then_shrink_b(env)
    env.worker.run_once()
    repair()

    env.service.retry("SYN-A")
    assert env.state("SYN-A") == "approved"  # a retry changes no state by itself
    env.worker.run_once()

    view = env.service.get_receipt("SYN-A")
    assert view.record.failed_stage is None and view.record.failed_reason is None
    assert view.record.state == "in_review"  # the result changed after the decision
    assert view.record.notice is not None and "after your decision" in view.record.notice
    assert any(isinstance(e, StageRetried) for e in env.events("SYN-A"))
    assert any(isinstance(e, NoticeRaised) for e in env.events("SYN-A"))


def test_a_retry_whose_result_is_unchanged_does_not_leave_the_receipt_in_limbo(
    env: ReviewEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    repair = fail_for(monkeypatch, "SYN-U")  # the notebook: nothing in the cascade changes it
    with env.stack.store.transaction() as tx:
        tx.enqueue("SYN-U", 1, "evaluate", env.stack.clock())
    env.worker.run_once()
    assert env.state("SYN-U") == "auto_approved"
    assert env.service.get_receipt("SYN-U").record.failed_stage == "evaluate"
    repair()

    env.service.retry("SYN-U")
    env.worker.run_once()

    view = env.service.get_receipt("SYN-U")
    assert view.record.state == "auto_approved"
    assert view.record.failed_stage is None
    assert view.allowed_actions == ("reject",)


def test_a_later_evaluation_that_succeeds_clears_the_failure_even_when_nothing_changed(
    env: ReviewEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    repair = fail_for(monkeypatch, "SYN-U")
    with env.stack.store.transaction() as tx:
        tx.enqueue("SYN-U", 1, "evaluate", env.stack.clock())
    env.worker.run_once()
    assert env.service.get_receipt("SYN-U").record.failed_stage == "evaluate"
    repair()

    with env.stack.store.transaction() as tx:  # another cascade reaches it, with no retry
        tx.enqueue("SYN-U", 1, "evaluate", env.stack.clock())
    env.worker.run_once()

    view = env.service.get_receipt("SYN-U")
    assert view.record.failed_stage is None and view.record.state == "auto_approved"


def test_a_receipt_that_was_never_evaluated_is_failed_and_retried_into_its_resting_state(
    env: ReviewEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    repair = fail_for(monkeypatch, "SYN-NEW")
    env.submit("SYN-NEW", "12.50", "Lunch A", employee_id="E-NEW", **MEAL)
    env.worker.run_once()
    assert env.state("SYN-NEW") == "failed"
    repair()

    env.service.retry("SYN-NEW")
    env.worker.run_once()
    assert env.state("SYN-NEW") in ("auto_approved", "in_review", "compliance")


def test_only_a_receipt_with_a_failure_can_be_retried(env: ReviewEnv) -> None:
    from expense_validator.app.errors import ActionNotAllowedError

    with pytest.raises(ActionNotAllowedError):
        env.service.retry("SYN-A")
