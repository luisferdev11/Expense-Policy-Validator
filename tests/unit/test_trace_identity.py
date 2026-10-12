"""One receipt revision is one trace (constitution X, ADR 0007 D11).

Classification and every stored evaluation version of a revision share a trace id: the label is
`app-r<revision>`. Each decision is its own `decide-receipt` observation in it, carrying its
evaluation version in the metadata, as the batch run does with its two top-level spans.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from tests.support import MEAL, ReviewEnv


@pytest.fixture
def env(tmp_path: Path) -> ReviewEnv:
    e = ReviewEnv(tmp_path)
    e.seed()
    return e


def traces(env: ReviewEnv, receipt_id: str) -> list[Any]:
    return [
        o
        for o in env.tracer.observations
        if o.kind == "trace" and o.fields.get("receipt_id") == receipt_id
    ]


def test_classification_and_decision_of_a_revision_share_one_trace_label(env: ReviewEnv) -> None:
    roots = traces(env, "SYN-A")
    assert {o.name for o in roots} == {"validate-receipt", "decide-receipt"}
    assert {o.fields["run_label"] for o in roots} == {"app-r1"}


def test_every_evaluation_version_is_a_decision_in_the_same_trace_with_its_version(
    env: ReviewEnv,
) -> None:
    env.submit("SYN-B", "10", "Lunch B", **MEAL)  # B shrinks: A is evaluated again (version 2)
    env.worker.run_once()

    decisions = [o for o in traces(env, "SYN-A") if o.name == "decide-receipt"]
    assert {o.fields["run_label"] for o in decisions} == {"app-r1"}
    versions = [
        u["metadata"]["evaluation_version"] for o in decisions for u in o.updates if "metadata" in u
    ]
    assert versions == [1, 2]


def test_a_correction_is_a_decision_of_the_same_trace(env: ReviewEnv) -> None:
    env.act("SYN-A", "correct-category", line_id="SYN-A-L1", category="lodging")
    decisions = [o for o in traces(env, "SYN-A") if o.name == "decide-receipt"]
    assert {o.fields["run_label"] for o in decisions} == {"app-r1"}
    assert len(decisions) == 2


def test_a_new_revision_is_a_new_trace(env: ReviewEnv) -> None:
    env.submit("SYN-A", "40", "Lunch A", attendee_count=2, **MEAL)
    env.worker.run_once()
    assert {o.fields["run_label"] for o in traces(env, "SYN-A")} == {"app-r1", "app-r2"}


def test_the_score_names_the_trace_of_the_revision_and_the_version_in_its_comment(
    env: ReviewEnv,
) -> None:
    env.act("SYN-A", "reject")
    score = env.tracer.scores[-1]
    assert (score["run_label"], score["receipt_id"]) == ("app-r1", "SYN-A")
    assert score["comment"].endswith("evaluation_version=1")
