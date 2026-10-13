"""The shadow stage: a second classifier's answers stored beside the deciding one (spec 007, US2).

The shadow never changes a state, a disposition, an evaluation or an event, never fails a receipt,
and never delays one. Doubles only: no network and no billed call.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any

import pytest

from expense_validator.adapters.openrouter.decision_classifier import DecisionClassifier
from expense_validator.adapters.sqlite_cache import SqliteClassificationCache
from expense_validator.adapters.sqlite_store import utc_now
from expense_validator.adapters.tracing import GuardedTracer
from expense_validator.app import worker as worker_module
from expense_validator.domain.events import StageFailed
from tests.fakes import BillingClassifier, RecordingTracer
from tests.support import DESCRIPTION, Stack, build_stack, notebook_classifier, receipt_json

NAME = "jev-hybrid"


def shadow_double(**kwargs: Any) -> BillingClassifier:
    """A shadow classifier that disagrees with the primary on the default line."""
    return BillingClassifier({DESCRIPTION: "tobacco"}, **kwargs)


def outbox(stack: Stack) -> list[tuple[str, str]]:
    with closing(sqlite3.connect(stack.store.path)) as conn:
        return conn.execute("SELECT stage, state FROM outbox ORDER BY id").fetchall()


def shadow_rows(stack: Stack, receipt_id: str = "SYN-1", revision: int = 1) -> list[Any]:
    with stack.store.transaction(write=False) as tx:
        return tx.shadow_for(receipt_id, revision)


def advance_and_drain(stack: Stack, worker: Any, rounds: int) -> None:
    """Run the queue, let every lease expire, and run it again."""
    for _ in range(rounds):
        worker.run_once()
        stack.clock.advance(worker_module.LEASE * 2)


def snapshot(stack: Stack, receipt_id: str = "SYN-1") -> dict[str, Any]:
    view = stack.service.get_receipt(receipt_id)
    with stack.store.transaction(write=False) as tx:
        events = [type(e.event).__name__ for e in tx.list_events(receipt_id)]
        versions = [e.version for e in tx.list_evaluations(receipt_id, 1)]
    r = view.record
    return {
        "state": r.state,
        "disposition": r.disposition,
        "evaluation_version": r.evaluation_version,
        "failed_stage": r.failed_stage,
        "failed_reason": r.failed_reason,
        "human_acted": r.human_acted,
        "result": view.result,
        "events": events,
        "versions": versions,
    }


@pytest.fixture
def stack(tmp_path: Path) -> Stack:
    return build_stack(tmp_path, RecordingTracer())


def test_with_shadow_off_no_shadow_work_is_queued_or_stored(stack: Stack) -> None:
    stack.service.submit(receipt_json())
    worker = stack.worker(notebook_classifier())
    assert worker.run_once() == 2  # classify, evaluate
    assert {stage for stage, _ in outbox(stack)} == {"classify", "evaluate"}
    assert shadow_rows(stack) == []


def test_with_shadow_on_the_classify_stage_queues_evaluate_and_shadow_together(
    stack: Stack,
) -> None:
    stack.service.submit(receipt_json())
    worker = stack.worker(notebook_classifier(), shadow=shadow_double(), shadow_name=NAME)
    assert worker.process_next() is True  # the classify stage only
    assert [(s, st) for s, st in outbox(stack)] == [
        ("classify", "done"),
        ("evaluate", "pending"),
        ("shadow", "pending"),
    ]
    assert worker.run_once() == 2


def test_the_shadow_stage_stores_one_row_per_line_with_the_shadow_identity(stack: Stack) -> None:
    stack.service.submit(receipt_json())
    shadow = shadow_double()
    stack.worker(notebook_classifier(), shadow=shadow, shadow_name=NAME).run_once()
    (row,) = shadow_rows(stack)
    assert (row.receipt_id, row.revision, row.line_id) == ("SYN-1", 1, "SYN-1-L1")
    assert (row.classifier, row.model_id, row.prompt_version) == (NAME, "fake-model", "test")
    assert (row.classification.status, row.classification.category) == ("classified", "tobacco")
    assert row.created_at.endswith("+00:00") and len(row.created_at) == 32
    assert shadow.calls_made == 1


def test_the_shadow_changes_nothing_about_the_receipt(tmp_path: Path) -> None:
    off = build_stack(tmp_path / "off")
    on = build_stack(tmp_path / "on")
    for s in (off, on):
        s.service.submit(receipt_json())
    off.worker(notebook_classifier()).run_once()
    on.worker(notebook_classifier(), shadow=shadow_double(), shadow_name=NAME).run_once()
    assert snapshot(on) == snapshot(off)
    assert snapshot(on)["failed_stage"] is None
    assert len(shadow_rows(on)) == 1 and shadow_rows(off) == []


def test_a_shadow_that_raises_ends_after_max_attempts_with_unclassified_rows(
    stack: Stack,
) -> None:
    stack.service.submit(receipt_json())
    calls: list[int] = []
    shadow = shadow_double(
        fail_with=RuntimeError("gateway down"), on_classify=lambda: calls.append(1)
    )
    worker = stack.worker(notebook_classifier(), shadow=shadow, shadow_name=NAME)
    advance_and_drain(stack, worker, rounds=worker_module.MAX_ATTEMPTS + 2)
    assert len(calls) == worker_module.MAX_ATTEMPTS
    (row,) = shadow_rows(stack)
    assert (row.classification.status, row.classification.unclassified_reason) == (
        "unclassified",
        "shadow_error",
    )
    assert row.classification.category is None
    assert [state for _, state in outbox(stack) if _ == "shadow"] == ["done"]
    after = snapshot(stack)
    assert after["state"] in ("auto_approved", "in_review") and after["failed_stage"] is None
    assert "StageFailed" not in after["events"]


@pytest.mark.parametrize("reason", ["gateway_error"])
def test_an_outage_reported_as_an_answer_is_retried_then_recorded(
    stack: Stack, reason: str
) -> None:
    stack.service.submit(receipt_json())
    shadow = shadow_double(unclassified_reasons={DESCRIPTION: reason})
    worker = stack.worker(notebook_classifier(), shadow=shadow, shadow_name=NAME)
    advance_and_drain(stack, worker, rounds=worker_module.MAX_ATTEMPTS + 2)
    (row,) = shadow_rows(stack)
    assert (row.classification.status, row.classification.unclassified_reason) == (
        "unclassified",
        reason,
    )
    assert snapshot(stack)["failed_stage"] is None


def test_a_refused_budget_is_recorded_at_once_without_retries(stack: Stack) -> None:
    stack.service.submit(receipt_json())
    calls: list[int] = []
    shadow = shadow_double(
        unclassified_reasons={DESCRIPTION: "budget_refused"}, on_classify=lambda: calls.append(1)
    )
    stack.worker(notebook_classifier(), shadow=shadow, shadow_name=NAME).run_once()
    (row,) = shadow_rows(stack)
    assert row.classification.unclassified_reason == "budget_refused"
    assert len(calls) == 1
    assert outbox(stack)[-1] == ("shadow", "done")


def test_a_newer_revision_makes_the_old_shadow_item_complete_without_storing(
    stack: Stack,
) -> None:
    stack.service.submit(receipt_json())
    worker = stack.worker(notebook_classifier(), shadow=shadow_double(), shadow_name=NAME)
    worker.process_next()  # classify: queues evaluate and shadow for revision 1
    now = stack.clock()
    with stack.store.transaction() as tx:
        # claim the shadow item as a worker would (evaluate is first in the queue)
        first = tx.claim_work(now, now + worker_module.LEASE)
        second = tx.claim_work(now, now + worker_module.LEASE)
    assert first is not None and second is not None and second.stage == "shadow"
    stack.service.submit(receipt_json(amount="99.00"))  # revision 2 replaces revision 1
    worker._shadow(second)
    assert shadow_rows(stack, revision=1) == []
    assert next(st for s, st in outbox(stack) if s == "shadow") == "done"


def test_the_shadow_classifier_is_a_separate_object_with_its_own_counters(stack: Stack) -> None:
    primary, shadow = notebook_classifier(), shadow_double()
    stack.service.submit(receipt_json())
    stack.worker(primary, shadow=shadow, shadow_name=NAME).run_once()
    assert primary.calls_made == 1 and shadow.calls_made == 1
    assert primary is not shadow


class JevTransport:
    """A fake decisions endpoint that bills 0.01 for every call."""

    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, payload: dict[str, Any]) -> tuple[dict[str, Any], str]:
        self.calls += 1
        body = {
            "id": f"jev-{self.calls}",
            "provider": "typesafe",
            "answers": {"category": {"choice": "tobacco", "probabilities": {"tobacco": 0.9}}},
            "usage": {"input_tokens": 700, "output_tokens": 10, "cost": 0.01},
        }
        return body, json.dumps(body)


def real_shadow(
    stack: Stack, tracer: RecordingTracer, transport: JevTransport, cap_usd: float, tmp_path: Path
) -> DecisionClassifier:
    return DecisionClassifier(
        SqliteClassificationCache(stack.store.path, utc_now),
        tracer,
        transport=transport,
        cap_usd=cap_usd,
        raw_dir=tmp_path / "raw",
    )


def test_the_shadow_cap_is_separate_from_the_primary(tmp_path: Path) -> None:
    tracer = RecordingTracer()
    stack = build_stack(tmp_path, tracer)
    stack.service.submit(receipt_json())
    transport = JevTransport()
    shadow = real_shadow(stack, tracer, transport, cap_usd=0.0, tmp_path=tmp_path)
    stack.worker(notebook_classifier(), shadow=shadow, shadow_name="jev-1.13").run_once()
    (row,) = shadow_rows(stack)
    assert row.classification.unclassified_reason == "budget_refused"
    assert transport.calls == 0
    assert snapshot(stack)["evaluation_version"] == 1  # the primary path was unaffected


def test_the_shadow_stage_is_traced_in_the_revisions_trace_without_model_names(
    tmp_path: Path,
) -> None:
    tracer = RecordingTracer()
    stack = build_stack(tmp_path, tracer)
    transport = JevTransport()
    shadow = real_shadow(stack, tracer, transport, cap_usd=1.0, tmp_path=tmp_path)
    worker = stack.worker(notebook_classifier(), shadow=shadow, shadow_name="jev-1.13")
    stack.service.submit(receipt_json("SYN-1"))
    stack.service.submit(receipt_json("SYN-2"))  # the same line text: its shadow answer is cached
    worker.run_once()
    roots = [o for o in tracer.observations if o.name == "shadow-classify-receipt"]
    assert len(roots) == 2
    assert {(o.kind, o.fields["run_label"]) for o in roots} == {("trace", "app-r1")}
    assert {o.fields["receipt_id"] for o in roots} == {"SYN-1", "SYN-2"}
    # one generation per billed shadow call, none on the cache hit (two primary calls are fakes)
    assert transport.calls == 1
    jev_generations = [
        o for o in tracer.named("classify-item") if o.fields["model"] == "typesafe/jev-1.13"
    ]
    assert len(jev_generations) == 1
    assert shadow.cache_hits == 1
    for observation in tracer.observations:
        assert "jev" not in observation.name and "gpt" not in observation.name


class LangfuseDown:
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


@pytest.mark.filterwarnings("ignore::expense_validator.adapters.tracing.TracingWarning")
def test_with_langfuse_down_the_shadow_rows_are_stored_and_the_receipt_is_unchanged(
    tmp_path: Path,
) -> None:
    quiet = build_stack(tmp_path / "quiet")
    down = build_stack(tmp_path / "down", GuardedTracer(LangfuseDown()))
    for s in (quiet, down):
        s.service.submit(receipt_json())
    quiet.worker(notebook_classifier()).run_once()
    down.worker(notebook_classifier(), shadow=shadow_double(), shadow_name=NAME).run_once()
    assert len(shadow_rows(down)) == 1
    assert snapshot(down) == snapshot(quiet)
    assert StageFailed.__name__ not in snapshot(down)["events"]
