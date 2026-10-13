"""The worker: stages, failure, retry, leases and stale work (ADR 0006, ADR 0007 D6, D11, D13)."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest

from expense_validator.adapters.config_files import load_settings
from expense_validator.adapters.tracing import NoopTracer
from expense_validator.app import worker as worker_module
from expense_validator.app.errors import ActionNotAllowedError
from expense_validator.app.pipeline import run_pipeline
from expense_validator.app.service import parse_receipt
from expense_validator.app.worker import scrub
from expense_validator.domain.events import (
    ReceiptClassified,
    ReceiptEvaluated,
    ReceiptSubmitted,
    StageFailed,
    StageRetried,
)
from tests.fakes import BillingClassifier, RecordingTracer, SimulatedCrash
from tests.support import (
    DESCRIPTION,
    MEAL,
    ReviewEnv,
    Stack,
    build_stack,
    notebook_classifier,
    receipt_json,
)


@pytest.fixture
def stack(tmp_path: Path) -> Stack:
    return build_stack(tmp_path)


def events(stack: Stack, receipt_id: str = "SYN-1") -> list[type]:
    with stack.store.transaction(write=False) as tx:
        return [type(e.event) for e in tx.list_events(receipt_id)]


def test_a_submitted_receipt_is_classified_then_evaluated(stack: Stack) -> None:
    stack.service.submit(receipt_json())
    worker = stack.worker(notebook_classifier())
    assert worker.run_once() == 2  # classify, evaluate
    view = stack.service.get_receipt("SYN-1")
    assert view.record.state in ("auto_approved", "in_review", "compliance")
    assert view.record.evaluation_version == 1 and view.result is not None
    assert events(stack) == [ReceiptSubmitted, ReceiptClassified, ReceiptEvaluated]


def test_the_stored_result_is_what_the_batch_pipeline_computes(stack: Stack) -> None:
    receipt = parse_receipt(receipt_json())
    expected = run_pipeline([receipt], notebook_classifier(), NoopTracer(), load_settings(), "t")[0]
    stack.service.submit(receipt_json())
    stack.worker(notebook_classifier()).run_once()
    assert stack.service.get_receipt("SYN-1").result == expected


def test_a_drained_queue_does_nothing(stack: Stack) -> None:
    assert stack.worker(notebook_classifier()).run_once() == 0


def test_a_failing_stage_leaves_the_receipt_failed_with_its_stage_and_reason(
    stack: Stack,
) -> None:
    stack.service.submit(receipt_json())
    stack.worker(notebook_classifier(fail_with=RuntimeError("gateway down"))).run_once()
    view = stack.service.get_receipt("SYN-1")
    assert view.record.state == "failed"
    assert (view.record.failed_stage, view.record.failed_reason) == (
        "classify",
        "RuntimeError: gateway down",
    )
    assert events(stack)[-1] is StageFailed


@pytest.mark.parametrize("reason", ["gateway_error", "budget_refused"])
def test_an_outage_reported_as_an_answer_fails_the_stage_and_keeps_nothing(
    stack: Stack, reason: str
) -> None:
    """The real adapter does not raise when the service is down or the budget is spent: it returns
    an unclassified line. Saving that would send a never-classified receipt to a person, and
    nothing would retry it (FR-015)."""
    stack.service.submit(receipt_json())
    outage = BillingClassifier(
        {DESCRIPTION: "office_supplies"}, unclassified_reasons={DESCRIPTION: reason}
    )
    stack.worker(outage).run_once()
    view = stack.service.get_receipt("SYN-1")
    assert view.record.state == "failed" and view.record.failed_stage == "classify"
    assert reason in (view.record.failed_reason or "")
    with stack.store.transaction(write=False) as tx:
        assert tx.load_classifications("SYN-1", 1) is None
    assert ReceiptClassified not in events(stack)

    stack.service.retry("SYN-1")
    stack.worker(notebook_classifier()).run_once()
    assert stack.service.get_receipt("SYN-1").record.state == "auto_approved"


@pytest.mark.parametrize("reason", ["schema_violation", "offline_cache_miss"])
def test_answers_that_are_final_stay_results_and_ask_for_review(stack: Stack, reason: str) -> None:
    stack.service.submit(receipt_json())
    final = BillingClassifier(
        {DESCRIPTION: "office_supplies"}, unclassified_reasons={DESCRIPTION: reason}
    )
    stack.worker(final).run_once()
    view = stack.service.get_receipt("SYN-1")
    assert view.record.state == "in_review" and view.record.disposition == "review"
    assert "EXC-03" in {s.rule_id for s in (view.result.review_signals if view.result else [])} | {
        e.rule_id for e in (view.result.exceptions if view.result else [])
    }


def test_a_failed_receipt_is_retried_from_the_stage_that_failed(stack: Stack) -> None:
    stack.service.submit(receipt_json())
    stack.worker(notebook_classifier(fail_with=RuntimeError("down"))).run_once()
    updated = stack.service.retry("SYN-1")
    assert updated.state == "submitted" and updated.failed_stage is None
    stack.worker(notebook_classifier()).run_once()
    assert stack.service.get_receipt("SYN-1").record.state != "failed"
    assert events(stack)[-4:] == [StageFailed, StageRetried, ReceiptClassified, ReceiptEvaluated]


def test_only_a_failed_receipt_can_be_retried(stack: Stack) -> None:
    stack.service.submit(receipt_json())
    with pytest.raises(ActionNotAllowedError, match="submitted"):
        stack.service.retry("SYN-1")


def test_a_failure_reason_never_carries_a_key() -> None:
    reason = scrub("Incorrect API key provided: sk-or-v1-abc123_DEF.ghi and more")
    assert "sk-or" not in reason and "[redacted]" in reason
    assert len(scrub("x" * 1000)) == 300


def test_a_crash_leaves_the_lease_and_work_resumes_after_it_expires(stack: Stack) -> None:
    stack.service.submit(receipt_json())
    with pytest.raises(SimulatedCrash):
        stack.worker(notebook_classifier(crash_after=0)).run_once()
    other = stack.worker(notebook_classifier())
    assert other.process_next() is False  # still leased to the dead worker
    stack.clock.advance(timedelta(seconds=61))
    assert other.run_once() == 2
    assert stack.service.get_receipt("SYN-1").record.evaluation_version == 1


def test_work_that_keeps_crashing_is_given_up_after_the_attempt_limit(stack: Stack) -> None:
    stack.service.submit(receipt_json())
    for _ in range(2):
        with pytest.raises(SimulatedCrash):
            stack.worker(notebook_classifier(crash_after=0), max_attempts=2).run_once()
        stack.clock.advance(timedelta(seconds=61))
    stack.worker(notebook_classifier(), max_attempts=2).run_once()
    view = stack.service.get_receipt("SYN-1")
    assert view.record.state == "failed"
    assert "gave up after 2 attempts" in (view.record.failed_reason or "")


def test_work_for_a_replaced_revision_is_dropped_without_a_trace_of_it(stack: Stack) -> None:
    stack.service.submit(receipt_json())
    replaced: list[bool] = []

    def revise() -> None:  # a new revision lands while the first one is being classified
        if not replaced:
            replaced.append(True)
            stack.service.submit(receipt_json(amount="99.00"))

    stack.worker(notebook_classifier(on_classify=revise)).run_once()
    stack.worker(notebook_classifier()).run_once()
    view = stack.service.get_receipt("SYN-1")
    assert view.record.current_revision == 2 and view.record.evaluation_version == 1
    with stack.store.transaction(write=False) as tx:
        assert tx.load_classifications("SYN-1", 1) is None  # revision 1 was never kept
        assert tx.load_classifications("SYN-1", 2) is not None


def test_an_evaluation_with_an_unchanged_result_records_nothing(stack: Stack) -> None:
    stack.service.submit(receipt_json())
    worker = stack.worker(notebook_classifier())
    worker.run_once()
    before = events(stack)
    with stack.store.transaction() as tx:
        tx.enqueue("SYN-1", 1, "evaluate", stack.clock())
    assert worker.run_once() == 1
    assert events(stack) == before
    with stack.store.transaction(write=False) as tx:
        assert len(tx.list_evaluations("SYN-1", 1)) == 1


def test_only_a_stored_evaluation_version_gets_a_decision_trace(tmp_path: Path) -> None:
    tracer = RecordingTracer()
    stack = build_stack(tmp_path, tracer)
    stack.service.submit(receipt_json())
    worker = stack.worker(notebook_classifier())
    worker.run_once()
    assert len(tracer.named("decide-receipt")) == 1
    with stack.store.transaction() as tx:
        tx.enqueue("SYN-1", 1, "evaluate", stack.clock())
    worker.run_once()
    assert len(tracer.named("decide-receipt")) == 1  # unchanged: nothing new to observe
    assert len(tracer.named("validate-receipt")) == 1  # one classification trace


# Decision fields (spec 006, US3)


def test_an_evaluation_to_auto_approved_is_decided_by_the_system_at_that_time(stack: Stack) -> None:
    stack.service.submit(receipt_json())
    stack.worker(notebook_classifier()).run_once()
    record = stack.service.get_receipt("SYN-1").record
    assert record.state == "auto_approved"
    evaluated_at = next(
        e.at for e in stack.service.list_events("SYN-1") if isinstance(e.event, ReceiptEvaluated)
    )
    assert (record.decided_by, record.decided_at) == ("system", evaluated_at)


def test_a_re_evaluation_that_sends_an_approved_receipt_back_to_review_clears_the_decision(
    tmp_path: Path,
) -> None:
    env = ReviewEnv(tmp_path)
    env.seed()
    env.act("SYN-A", "approve", reason_code="policy_exception_granted")
    assert env.service.get_receipt("SYN-A").record.decided_by == "alice"
    env.submit("SYN-B", "10", "Lunch B", **MEAL)  # B shrinks: A's result changes (ADR 0007 D7)
    env.worker.run_once()
    record = env.service.get_receipt("SYN-A").record
    assert record.state == "in_review" and record.notice is not None
    assert (record.decided_by, record.decided_at) == (None, None)


def test_a_failed_re_evaluation_keeps_the_state_and_the_decision_and_does_not_ask_the_rule(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env = ReviewEnv(tmp_path)
    env.seed()
    env.act("SYN-A", "approve", reason_code="policy_exception_granted")
    before = env.service.get_receipt("SYN-A").record

    original = worker_module.build_evaluation

    def failing(tx: object, settings: object, meta: object, rid: str, revision: int) -> object:
        if rid == "SYN-A":
            raise RuntimeError("the store was busy")
        return original(tx, settings, meta, rid, revision)  # type: ignore[arg-type]

    asked: list[str] = []
    real_rule = worker_module.decision_after

    def spy(new_state: str, **kwargs: object) -> tuple[str | None, str | None]:
        asked.append(new_state)
        return real_rule(new_state, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(worker_module, "build_evaluation", failing)
    monkeypatch.setattr(worker_module, "decision_after", spy)
    env.submit("SYN-B", "10", "Lunch B", **MEAL)
    env.worker.run_once()

    after = env.service.get_receipt("SYN-A").record
    assert after.failed_stage == "evaluate" and after.state == "approved"
    assert (after.decided_by, after.decided_at) == (before.decided_by, before.decided_at)
    assert "approved" not in asked  # `_fail` kept the state, so it never asked the rule
