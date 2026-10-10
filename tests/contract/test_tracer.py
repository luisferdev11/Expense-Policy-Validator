"""The tracer never gates a run (T017, FR-026, FR-028, contracts/tracing.md)."""

from __future__ import annotations

import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import pytest

from expense_validator.adapters.tracing import (
    GuardedTracer,
    NoopTracer,
    TracingWarning,
    make_tracer,
)
from expense_validator.ports.tracer import Observation, Tracer


def test_noop_tracer_satisfies_the_protocol() -> None:
    tracer = NoopTracer()
    assert isinstance(tracer, Tracer)
    with tracer.receipt_trace("SYN-1", run_label="t", input={}) as root:
        root.update(output={"ok": True})
        with tracer.span("normalise-receipt") as span:
            span.update(output=[])
        with tracer.generation("classify-item", model="m", input=[]) as gen:
            gen.update(output="{}")
    tracer.flush(timeout_s=0.1)


def test_missing_keys_give_noop_with_one_warning() -> None:
    with pytest.warns(TracingWarning) as record:
        tracer = make_tracer(env={})
    assert len(record) == 1
    assert not tracer.enabled


def test_disabled_flag_gives_noop_without_warning() -> None:
    tracer = make_tracer(env={}, disabled=True)
    assert not tracer.enabled


class _Exploding:
    enabled = True

    @contextmanager
    def receipt_trace(
        self, receipt_id: str, run_label: str, input: Any, name: str = "validate-receipt"
    ) -> Iterator[Observation]:
        raise RuntimeError("server gone")
        yield  # pragma: no cover

    @contextmanager
    def span(self, name: str, input: Any = None) -> Iterator[Observation]:
        raise RuntimeError("server gone")
        yield  # pragma: no cover

    @contextmanager
    def generation(self, name: str, model: str, input: Any) -> Iterator[Observation]:
        raise RuntimeError("server gone")
        yield  # pragma: no cover

    def flush(self, timeout_s: float = 5.0) -> None:
        raise RuntimeError("server gone")


def test_a_failing_tracer_is_swapped_for_noop_once() -> None:
    guarded = GuardedTracer(_Exploding())
    with pytest.warns(TracingWarning) as record:
        with guarded.receipt_trace("SYN-1", run_label="t", input={}) as root:
            root.update(output=1)
        with guarded.span("apply-rules") as span:
            span.update(output=2)
    assert len(record) == 1
    assert not guarded.enabled


class _BlockingFlush(NoopTracer):
    enabled = True

    def __init__(self) -> None:
        self.release = threading.Event()

    def flush(self, timeout_s: float = 5.0) -> None:
        self.release.wait()


def test_flush_is_bounded_by_its_timeout() -> None:
    inner = _BlockingFlush()
    guarded = GuardedTracer(inner)
    start = time.monotonic()
    with pytest.warns(TracingWarning):
        guarded.flush(timeout_s=0.2)
    assert time.monotonic() - start < 2.0
    inner.release.set()


class _RecordingClient:
    def __init__(self) -> None:
        self.scores: list[dict[str, Any]] = []

    def create_score(self, **fields: Any) -> None:
        self.scores.append(fields)


def test_noop_tracer_accepts_a_score() -> None:
    NoopTracer().score("app-r1-v1", "SYN-1", "auditor_agreement", 1.0, "approve")


def test_the_langfuse_tracer_posts_a_numeric_score_on_the_deterministic_trace() -> None:
    from expense_validator.adapters.tracing import LangfuseTracer, trace_id_for

    client = _RecordingClient()
    LangfuseTracer(client).score("app-r2-v3", "SYN-1", "auditor_agreement", 0.0, "reject")
    assert client.scores == [
        {
            "name": "auditor_agreement",
            "value": 0.0,
            "trace_id": trace_id_for("app-r2-v3", "SYN-1"),
            "comment": "reject",
            "data_type": "NUMERIC",
        }
    ]


class _ExplodingScore(NoopTracer):
    enabled = True

    def score(
        self, run_label: str, receipt_id: str, name: str, value: float, comment: str | None = None
    ) -> None:
        raise RuntimeError("server gone")


def test_a_failing_score_never_raises_and_disables_tracing_once() -> None:
    guarded = GuardedTracer(_ExplodingScore())
    with pytest.warns(TracingWarning) as record:
        guarded.score("app-r1-v1", "SYN-1", "auditor_agreement", 1.0, "approve")
        guarded.score("app-r1-v1", "SYN-1", "auditor_agreement", 1.0, "approve")
    assert len(record) == 1
    assert not guarded.enabled
