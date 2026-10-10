"""With Langfuse down, intake, processing and reviewer actions still complete, with identical
results (SC-006, constitution X: Langfuse never gates a run).

The same scenario runs twice: once untraced, once through the guarded tracer wrapped around a
tracer whose every operation raises, as when the server is unreachable mid-run.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from expense_validator.adapters.tracing import GuardedTracer, NoopTracer
from expense_validator.app.reviewing import ActionRequest, ReviewService
from expense_validator.ports.tracer import Tracer
from tests.fakes import BillingClassifier
from tests.support import (
    DESCRIPTION,
    MEAL,
    REVIEW_CATEGORIES,
    REVIEW_RECIPIENTS,
    build_stack,
    receipt_json,
)

pytestmark = pytest.mark.filterwarnings("ignore::expense_validator.adapters.tracing.TracingWarning")

IDS = ["SYN-A", "SYN-B", "SYN-U", "SYN-G"]


class LangfuseDown:
    """A tracer for a server that cannot be reached: every operation fails."""

    enabled = True

    def receipt_trace(self, *args: Any, **kwargs: Any) -> Any:
        raise ConnectionError("langfuse is down")

    def span(self, *args: Any, **kwargs: Any) -> Any:
        raise ConnectionError("langfuse is down")

    def generation(self, *args: Any, **kwargs: Any) -> Any:
        raise ConnectionError("langfuse is down")

    def score(self, *args: Any, **kwargs: Any) -> None:
        raise ConnectionError("langfuse is down")

    def flush(self, timeout_s: float = 5.0) -> None:
        raise ConnectionError("langfuse is down")


def scenario(tmp_path: Path, tracer: Tracer) -> dict[str, Any]:
    stack = build_stack(tmp_path, tracer)
    review = ReviewService(stack.store, stack.clock, stack.service, tracer=tracer)
    worker = stack.worker(
        BillingClassifier(REVIEW_CATEGORIES, recipients=REVIEW_RECIPIENTS), tracer
    )
    for rid, amount, description, extra in [
        ("SYN-A", "40", "Lunch A", MEAL),
        ("SYN-B", "50", "Lunch B", MEAL),
        ("SYN-U", "12.50", DESCRIPTION, {"employee_id": "E-U"}),
        ("SYN-G", "30", "Gift basket", {"employee_id": "E-G"}),
    ]:
        stack.service.submit(receipt_json(rid, amount, description, **extra))
    worker.run_once()

    def version(rid: str) -> int:
        found = stack.service.get_receipt(rid).record.evaluation_version
        assert found is not None
        return found

    outcomes = {
        "reject": review.act("SYN-G", "reject", ActionRequest("alice", version("SYN-G"))),
        "correct": review.act(
            "SYN-A",
            "correct-category",
            ActionRequest("alice", version("SYN-A"), line_id="SYN-A-L1", category="lodging"),
        ),
    }
    worker.run_once()
    views = {rid: stack.service.get_receipt(rid) for rid in IDS}
    return {
        "states": {rid: v.record.state for rid, v in views.items()},
        "results": {rid: v.result for rid, v in views.items()},
        "agreements": {name: o.agreement for name, o in outcomes.items()},
    }


def test_nothing_fails_and_nothing_changes_when_langfuse_is_down(tmp_path: Path) -> None:
    untraced = scenario(tmp_path / "untraced", NoopTracer())
    guarded = GuardedTracer(LangfuseDown())
    down = scenario(tmp_path / "down", guarded)

    assert not guarded.enabled  # the dead tracer was really used, and was switched off
    assert "failed" not in down["states"].values()
    assert down["states"] == untraced["states"]
    assert down["results"] == untraced["results"]
    assert down["agreements"] == untraced["agreements"] == {"reject": 1, "correct": 0}
    assert all(result is not None for result in down["results"].values())
