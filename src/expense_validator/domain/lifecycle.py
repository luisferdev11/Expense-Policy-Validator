"""The receipt lifecycle as pure functions (ADR 0006 decision 5, ADR 0007 D7 and D8).

`evaluated` is an event, not a resting state: an evaluation moves a receipt straight to the state
of its disposition. A human decision is never silently overwritten by a later evaluation.
"""

from __future__ import annotations

from typing import Literal, get_args

from expense_validator.domain.models import Disposition

State = Literal[
    "submitted",
    "classifying",
    "auto_approved",
    "in_review",
    "compliance",
    "needs_info",
    "approved",
    "rejected",
    "failed",
]
Action = Literal["approve", "reject", "correct-category", "request-info", "escalate"]
Stage = Literal["classify", "evaluate"]

ACTIONS: tuple[Action, ...] = get_args(Action)

_ALLOWED: dict[State, tuple[Action, ...]] = {
    "in_review": ("approve", "reject", "correct-category", "request-info", "escalate"),
    "compliance": ("approve", "reject", "correct-category", "request-info"),
    "auto_approved": ("reject",),
    "needs_info": ("reject",),
}

_AFTER_ACTION: dict[Action, State] = {
    "approve": "approved",
    "reject": "rejected",
    "request-info": "needs_info",
    "escalate": "compliance",
}


class NotAllowedError(Exception):
    """The current state does not allow the action."""


def allowed_actions(state: State) -> tuple[Action, ...]:
    return _ALLOWED.get(state, ())


def require_allowed(state: State, action: Action) -> None:
    if action not in allowed_actions(state):
        raise NotAllowedError(f"action {action!r} is not allowed in state {state!r}")


def state_after_action(action: Action) -> State:
    """The state a closing or routing action leads to. A category correction has none: the
    engine runs again and the new evaluation decides."""
    if action == "correct-category":
        raise ValueError("a category correction needs a re-evaluation to pick its state")
    return _AFTER_ACTION[action]


def state_for_evaluation(disposition: Disposition, critical: bool) -> State:
    if critical:
        return "compliance"
    return "auto_approved" if disposition == "pass" else "in_review"


def state_after_correction(proposed: State) -> State:
    """After a reviewer's correction the receipt still waits for a human decision, even if it
    would now pass; a critical finding keeps it with Compliance."""
    return "in_review" if proposed == "auto_approved" else proposed


def reevaluation_outcome(
    previous: State, human_acted: bool, new_state: State
) -> tuple[State, bool]:
    """State and notice flag after a re-evaluation that changed the result (ADR 0007 D7)."""
    if human_acted or previous in ("approved", "rejected", "needs_info"):
        return ("in_review" if new_state == "auto_approved" else new_state), True
    if previous == "auto_approved":
        return new_state, new_state != "auto_approved"
    return new_state, False
