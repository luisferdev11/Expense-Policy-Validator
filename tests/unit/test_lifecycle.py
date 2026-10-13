"""The receipt lifecycle (ADR 0006 decision 5, ADR 0007 D7 and D8, data-model.md)."""

from __future__ import annotations

import pytest

from expense_validator.domain.lifecycle import (
    ACTIONS,
    SYSTEM_ACTOR,
    NotAllowedError,
    allowed_actions,
    decision_after,
    reevaluation_outcome,
    require_allowed,
    state_after_action,
    state_for_evaluation,
)


@pytest.mark.parametrize(
    ("disposition", "critical", "expected"),
    [
        ("pass", False, "auto_approved"),
        ("review", False, "in_review"),
        ("flag", False, "in_review"),
        ("flag", True, "compliance"),
    ],
)
def test_a_first_evaluation_goes_to_the_state_of_its_disposition(
    disposition: str, critical: bool, expected: str
) -> None:
    assert state_for_evaluation(disposition, critical) == expected  # type: ignore[arg-type]


def test_allowed_actions_by_state() -> None:
    assert allowed_actions("in_review") == (
        "approve",
        "reject",
        "correct-category",
        "request-info",
        "escalate",
    )
    assert "escalate" not in allowed_actions("compliance")
    assert allowed_actions("auto_approved") == ("reject",)
    assert allowed_actions("needs_info") == ("reject",)
    for state in ("submitted", "classifying", "approved", "rejected", "failed"):
        assert allowed_actions(state) == ()  # type: ignore[arg-type]


def test_every_action_is_allowed_somewhere() -> None:
    covered = {
        a
        for s in ("in_review", "compliance", "auto_approved", "needs_info")
        for a in allowed_actions(s)
    }  # type: ignore[arg-type]
    assert covered == set(ACTIONS)


def test_a_disallowed_action_raises() -> None:
    with pytest.raises(NotAllowedError, match="approved"):
        require_allowed("approved", "approve")


@pytest.mark.parametrize(
    ("action", "expected"),
    [
        ("approve", "approved"),
        ("reject", "rejected"),
        ("request-info", "needs_info"),
        ("escalate", "compliance"),
    ],
)
def test_state_after_a_closing_or_routing_action(action: str, expected: str) -> None:
    assert state_after_action(action) == expected  # type: ignore[arg-type]


def test_correct_category_has_no_fixed_state() -> None:
    with pytest.raises(ValueError, match="re-evaluation"):
        state_after_action("correct-category")


def test_an_untouched_receipt_in_the_queue_follows_the_new_proposal_silently() -> None:
    assert reevaluation_outcome("in_review", human_acted=False, new_state="compliance") == (
        "compliance",
        False,
    )
    assert reevaluation_outcome("in_review", human_acted=False, new_state="auto_approved") == (
        "auto_approved",
        False,
    )


def test_an_auto_approved_receipt_raises_a_notice_only_when_it_needs_review_now() -> None:
    assert reevaluation_outcome("auto_approved", False, "auto_approved") == ("auto_approved", False)
    assert reevaluation_outcome("auto_approved", False, "in_review") == ("in_review", True)
    assert reevaluation_outcome("auto_approved", False, "compliance") == ("compliance", True)


@pytest.mark.parametrize("previous", ["approved", "rejected", "needs_info", "in_review"])
def test_a_human_decision_is_never_silently_overwritten(previous: str) -> None:
    assert reevaluation_outcome(previous, True, "auto_approved") == ("in_review", True)  # type: ignore[arg-type]
    assert reevaluation_outcome(previous, True, "in_review") == ("in_review", True)  # type: ignore[arg-type]
    assert reevaluation_outcome(previous, True, "compliance") == ("compliance", True)  # type: ignore[arg-type]


# Who decided and when (spec 006, data-model.md section 4)

AT = "2026-10-12T15:00:00.000000+00:00"


@pytest.mark.parametrize("new_state", ["approved", "rejected"])
def test_a_reviewers_closing_action_keeps_the_actor_and_the_time(new_state: str) -> None:
    # `rejected` is reached from in_review, compliance, auto_approved and needs_info alike: the
    # rule sees only the new state, so one case stands for all four.
    assert decision_after(new_state, actor="alice", at=AT, by_human_action=True) == ("alice", AT)  # type: ignore[arg-type]


def test_an_evaluation_that_auto_approves_is_the_systems_decision() -> None:
    assert decision_after("auto_approved", actor="worker", at=AT, by_human_action=False) == (
        SYSTEM_ACTOR,
        AT,
    )
    assert SYSTEM_ACTOR == "system"


@pytest.mark.parametrize("by_human", [False, True])
@pytest.mark.parametrize(
    "new_state",
    ["in_review", "compliance", "needs_info", "submitted", "classifying", "failed"],
)
def test_every_other_state_has_no_decision(new_state: str, by_human: bool) -> None:
    # in_review and compliance after an evaluation or a correction; needs_info after request-info;
    # compliance after escalate; submitted after a new revision or a retry; failed after a failure.
    assert decision_after(new_state, actor="alice", at=AT, by_human_action=by_human) == (  # type: ignore[arg-type]
        None,
        None,
    )


@pytest.mark.parametrize("new_state", ["approved", "rejected"])
def test_approved_and_rejected_are_only_reached_by_a_human_action(new_state: str) -> None:
    with pytest.raises(ValueError, match="human"):
        decision_after(new_state, actor="alice", at=AT, by_human_action=False)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="actor"):
        decision_after(new_state, actor=None, at=AT, by_human_action=True)  # type: ignore[arg-type]
