"""Reviewer actions on real receipts through the real engine (ADR 0006 decision 6, ADR 0007 D8-D10).

Receipts: SYN-A and SYN-B are two lunches of one employee-day, 40 + 50 > 75 (MEAL-01, flag, so
`in_review`). SYN-U is a notebook (pass, so `auto_approved`). SYN-G is a gift for a government
official (GIFT-04, critical, so `compliance`).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from expense_validator.app.errors import (
    ActionNotAllowedError,
    InvalidActionError,
    NotFoundError,
    ReasonRequiredError,
    StaleEvaluationError,
    UnknownCategoryError,
)
from expense_validator.app.reviewing import ActionRequest, ReviewService
from expense_validator.domain.events import (
    DevCandidateMarked,
    EscalatedToCompliance,
    InformationRequested,
    LineCategoryCorrected,
    ReceiptApproved,
    ReceiptRejected,
)
from tests.fakes import RecordingTracer
from tests.support import DESCRIPTION, MEAL
from tests.support import ReviewEnv as Env


@pytest.fixture
def env(tmp_path: Path) -> Env:
    e = Env(tmp_path)
    e.seed()
    return e


def test_the_seeded_receipts_start_where_the_lifecycle_puts_them(env: Env) -> None:
    assert env.state("SYN-A") == env.state("SYN-B") == "in_review"
    assert env.state("SYN-U") == "auto_approved"
    assert env.state("SYN-G") == "compliance"


# Approve and reject


def test_approving_a_flagged_receipt_needs_a_reason_code(env: Env) -> None:
    with pytest.raises(ReasonRequiredError, match="flag"):
        env.act("SYN-A", "approve")
    assert env.state("SYN-A") == "in_review"  # nothing changed
    assert not any(isinstance(e, ReceiptApproved) for e in env.events("SYN-A"))


def test_an_approval_that_overrides_the_engine_records_the_reason_and_disagreement(
    env: Env,
) -> None:
    result = env.act("SYN-A", "approve", reason_code="policy_exception_granted", note="VP ok")
    assert result.agreement == 0
    view = env.service.get_receipt("SYN-A")
    assert view.record.state == "approved" and view.record.human_acted is True
    assert view.allowed_actions == ()
    approved = env.events("SYN-A")[-1]
    assert isinstance(approved, ReceiptApproved)
    assert (approved.reason_code, approved.note, approved.agreement) == (
        "policy_exception_granted",
        "VP ok",
        0,
    )
    assert env.service.list_events("SYN-A")[-1].actor == "alice"


def test_rejecting_a_flagged_receipt_agrees_with_the_engine_and_needs_no_reason(env: Env) -> None:
    result = env.act("SYN-A", "reject")
    assert result.agreement == 1 and env.state("SYN-A") == "rejected"
    assert isinstance(env.events("SYN-A")[-1], ReceiptRejected)


def test_rejecting_an_auto_approved_receipt_overrides_the_engine_and_needs_a_reason(
    env: Env,
) -> None:
    with pytest.raises(ReasonRequiredError):
        env.act("SYN-U", "reject")
    result = env.act("SYN-U", "reject", reason_code="engine_missed_issue")
    assert result.agreement == 0 and env.state("SYN-U") == "rejected"


def test_the_reason_code_other_needs_a_note_and_unknown_codes_are_refused(env: Env) -> None:
    with pytest.raises(ReasonRequiredError, match="note"):
        env.act("SYN-A", "approve", reason_code="other")
    with pytest.raises(InvalidActionError, match="reason code"):
        env.act("SYN-A", "approve", reason_code="because")
    assert env.act("SYN-A", "approve", reason_code="other", note="see email").agreement == 0


def test_approve_is_not_allowed_on_an_auto_approved_receipt(env: Env) -> None:
    with pytest.raises(ActionNotAllowedError, match="auto_approved"):
        env.act("SYN-U", "approve")


# Request information and escalate


def test_requesting_information_waits_for_the_employee_and_a_revision_answers(env: Env) -> None:
    with pytest.raises(InvalidActionError, match="question"):
        env.act("SYN-A", "request-info")
    result = env.act("SYN-A", "request-info", question="Who attended?")
    assert result.agreement == 1 and env.state("SYN-A") == "needs_info"
    asked = env.events("SYN-A")[-1]
    assert isinstance(asked, InformationRequested) and asked.question == "Who attended?"

    env.submit("SYN-A", "40", "Lunch A", attendee_count=2, **MEAL)  # the employee answers
    view = env.service.get_receipt("SYN-A")
    assert (view.record.current_revision, view.record.state) == (2, "submitted")
    assert view.record.human_acted is False
    env.worker.run_once()
    # two attendees: 20 per person, plus B's 50, is within the 75 cap, so the answer resolves it
    assert env.state("SYN-A") == "auto_approved"


def test_escalating_sends_the_receipt_to_compliance_and_only_from_review(env: Env) -> None:
    with pytest.raises(InvalidActionError, match="reason"):
        env.act("SYN-A", "escalate")
    result = env.act("SYN-A", "escalate", reason="possible split bill")
    assert result.agreement == 1 and env.state("SYN-A") == "compliance"
    assert isinstance(env.events("SYN-A")[-1], EscalatedToCompliance)
    with pytest.raises(ActionNotAllowedError):
        env.act("SYN-A", "escalate", reason="again")


def test_a_critical_finding_is_already_with_compliance_and_can_be_decided_there(env: Env) -> None:
    assert env.state("SYN-G") == "compliance"
    assert env.act("SYN-G", "reject").agreement == 1
    assert env.state("SYN-G") == "rejected"


def test_a_reject_is_possible_from_needs_info(env: Env) -> None:
    env.act("SYN-A", "request-info", question="Who attended?")
    assert env.act("SYN-A", "reject").agreement == 1
    assert env.state("SYN-A") == "rejected"


# Guards


def test_a_stale_evaluation_version_is_refused_with_the_current_one(env: Env) -> None:
    with pytest.raises(StaleEvaluationError) as raised:
        env.act("SYN-A", "reject", evaluation_version=99)
    assert raised.value.details == {"current_evaluation_version": 1}
    assert env.state("SYN-A") == "in_review"


def test_unknown_receipts_and_missing_actors_are_refused(env: Env) -> None:
    with pytest.raises(NotFoundError):
        env.act("NOPE", "reject", evaluation_version=1)
    with pytest.raises(InvalidActionError, match="actor"):
        env.act("SYN-A", "reject", actor="  ")


def test_nothing_can_be_done_to_a_receipt_still_in_processing(tmp_path: Path) -> None:
    e = Env(tmp_path)
    e.submit("SYN-1", "12.50", DESCRIPTION)
    with pytest.raises(ActionNotAllowedError, match="submitted"):
        e.act("SYN-1", "reject", evaluation_version=1)


# Correct a category


def test_correcting_a_category_re_runs_the_engine_with_the_human_category(env: Env) -> None:
    before = env.service.get_receipt("SYN-A")
    assert before.result is not None and "MEAL-01" in {e.rule_id for e in before.result.exceptions}

    result = env.act("SYN-A", "correct-category", line_id="SYN-A-L1", category="lodging")

    assert result.agreement == 0
    view = env.service.get_receipt("SYN-A")
    assert view.record.evaluation_version == 2 and view.record.human_acted is True
    assert view.record.notice is None and view.record.state in ("in_review", "compliance")
    assert view.result is not None
    line = view.result.line_items[0]
    assert (line.category, line.confidence) == ("lodging", 1.0)
    assert "MEAL-01" not in {e.rule_id for e in view.result.exceptions}  # no longer a meal
    kinds = [type(e) for e in env.events("SYN-A")]
    assert kinds[-3:] == [LineCategoryCorrected, DevCandidateMarked, kinds[-1]]
    corrected = next(e for e in env.events("SYN-A") if isinstance(e, LineCategoryCorrected))
    assert (corrected.from_category, corrected.to_category) == ("food_beverage", "lodging")
    candidate = next(e for e in env.events("SYN-A") if isinstance(e, DevCandidateMarked))
    assert (candidate.line_id, candidate.to_category) == ("SYN-A-L1", "lodging")


def test_a_correction_that_removes_a_finding_still_waits_for_a_human(env: Env) -> None:
    env.act("SYN-A", "correct-category", line_id="SYN-A-L1", category="lodging")
    assert env.state("SYN-A") == "in_review"  # it passes now, but a human decides


def test_a_correction_refreshes_the_receipts_it_shares_a_day_with(env: Env) -> None:
    env.act("SYN-A", "correct-category", line_id="SYN-A-L1", category="lodging")
    env.worker.run_once()  # the neighbour's evaluation was queued, not run inline
    other = env.service.get_receipt("SYN-B").result
    assert other is not None and "MEAL-01" not in {e.rule_id for e in other.exceptions}


def test_a_human_category_survives_later_re_evaluations(env: Env) -> None:
    env.act("SYN-A", "correct-category", line_id="SYN-A-L1", category="lodging")
    env.submit("SYN-C", "20", "Lunch B", **MEAL)  # a new neighbour triggers the cascade
    env.worker.run_once()
    result = env.service.get_receipt("SYN-A").result
    assert result is not None and result.line_items[0].category == "lodging"


def test_the_correction_is_validated(env: Env) -> None:
    with pytest.raises(InvalidActionError, match="line_id"):
        env.act("SYN-A", "correct-category", category="lodging")
    with pytest.raises(InvalidActionError, match="category"):
        env.act("SYN-A", "correct-category", line_id="SYN-A-L1")
    with pytest.raises(UnknownCategoryError):
        env.act("SYN-A", "correct-category", line_id="SYN-A-L1", category="spaceship")
    with pytest.raises(InvalidActionError, match="no line"):
        env.act("SYN-A", "correct-category", line_id="SYN-A-L9", category="lodging")
    with pytest.raises(InvalidActionError, match="already"):
        env.act("SYN-A", "correct-category", line_id="SYN-A-L1", category="food_beverage")
    assert env.service.get_receipt("SYN-A").record.evaluation_version == 1


def test_a_second_correction_replaces_the_first(env: Env) -> None:
    env.act("SYN-A", "correct-category", line_id="SYN-A-L1", category="lodging")
    env.act("SYN-A", "correct-category", line_id="SYN-A-L1", category="airfare")
    result = env.service.get_receipt("SYN-A")
    assert result.result is not None and result.result.line_items[0].category == "airfare"
    assert result.record.evaluation_version == 3


# After a decision


def test_a_decided_receipt_returns_to_the_queue_with_a_notice_when_the_result_changes(
    env: Env,
) -> None:
    env.act("SYN-A", "approve", reason_code="policy_exception_granted")
    assert env.state("SYN-A") == "approved"
    env.submit("SYN-B", "10", "Lunch B", **MEAL)  # B shrinks: A's day is within the cap again
    env.worker.run_once()
    view = env.service.get_receipt("SYN-A")
    assert view.record.state == "in_review"
    assert view.record.notice is not None and "after your decision" in view.record.notice
    assert env.service.get_receipt("SYN-A").record.disposition == "pass"
    # the earlier approval stays in the trail
    assert any(isinstance(e, ReceiptApproved) for e in env.events("SYN-A"))
    # and the next action clears the notice
    env.act("SYN-A", "approve")
    assert env.service.get_receipt("SYN-A").record.notice is None


# Scores


def test_every_action_posts_an_agreement_score_on_the_trace_of_the_version_it_was_based_on(
    env: Env,
) -> None:
    env.act("SYN-A", "reject")
    env.act("SYN-U", "reject", reason_code="engine_missed_issue")
    assert env.tracer.scores == [
        {
            "run_label": "app-r1-v1",
            "receipt_id": "SYN-A",
            "name": "auditor_agreement",
            "value": 1.0,
            "comment": "reject; proposal=flag",
        },
        {
            "run_label": "app-r1-v1",
            "receipt_id": "SYN-U",
            "name": "auditor_agreement",
            "value": 0.0,
            "comment": "reject; proposal=pass; reason_code=engine_missed_issue",
        },
    ]


def test_a_failing_tracer_never_fails_an_action(env: Env) -> None:
    class Exploding(RecordingTracer):
        def score(self, *args: Any, **kwargs: Any) -> None:
            raise RuntimeError("langfuse is down")

    review = ReviewService(env.stack.store, env.stack.clock, env.service, tracer=Exploding())
    view = env.service.get_receipt("SYN-A")
    result = review.act(
        "SYN-A", "reject", ActionRequest("alice", view.record.evaluation_version or 0)
    )
    assert result.agreement == 1 and env.state("SYN-A") == "rejected"


def test_a_scored_correction_also_traces_the_new_decision(env: Env) -> None:
    before = len(env.tracer.named("decide-receipt"))
    env.act("SYN-A", "correct-category", line_id="SYN-A-L1", category="lodging")
    assert len(env.tracer.named("decide-receipt")) == before + 1
    assert env.tracer.scores[-1]["comment"] == "correct-category; proposal=flag"
