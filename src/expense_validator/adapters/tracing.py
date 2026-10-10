"""Tracer adapters: Langfuse when available, a no-op otherwise. Tracing never gates a run.

Implements CLAUDE.md rule 11 and contracts/tracing.md. `make_tracer` returns a `GuardedTracer`:
any tracer error switches it to no-op with one warning, and `flush` is bounded by a timeout,
because the Langfuse SDK's own `flush()` blocks (research R6).
"""

from __future__ import annotations

import os
import threading
import warnings
from collections.abc import Callable, Iterator, Mapping
from contextlib import AbstractContextManager, contextmanager, nullcontext
from typing import Any

from expense_validator.ports.tracer import Observation, Tracer


class TracingWarning(UserWarning):
    """Tracing was disabled or degraded; outputs are unaffected."""


class _NoopObservation:
    def update(self, **fields: Any) -> None:
        return None


_NOOP_OBSERVATION = _NoopObservation()


class NoopTracer:
    enabled = False

    def receipt_trace(
        self, receipt_id: str, run_label: str, input: Any, name: str = "validate-receipt"
    ) -> AbstractContextManager[Observation]:
        return nullcontext(_NOOP_OBSERVATION)

    def span(self, name: str, input: Any = None) -> AbstractContextManager[Observation]:
        return nullcontext(_NOOP_OBSERVATION)

    def generation(
        self, name: str, model: str, input: Any, **fields: Any
    ) -> AbstractContextManager[Observation]:
        return nullcontext(_NOOP_OBSERVATION)

    def score(
        self, run_label: str, receipt_id: str, name: str, value: float, comment: str | None = None
    ) -> None:
        return None

    def flush(self, timeout_s: float = 5.0) -> None:
        return None


def trace_id_for(run_label: str, receipt_id: str) -> str:
    """Deterministic Langfuse trace id for one receipt of one run."""
    from langfuse import Langfuse

    trace_id: str = Langfuse.create_trace_id(seed=f"{run_label}:{receipt_id}")
    return trace_id


class LangfuseTracer:
    """Adapter over the Langfuse Python SDK (v3+ API, verified on 4.17)."""

    enabled = True

    def __init__(self, client: Any) -> None:
        self.client = client

    def receipt_trace(
        self, receipt_id: str, run_label: str, input: Any, name: str = "validate-receipt"
    ) -> AbstractContextManager[Observation]:
        cm: AbstractContextManager[Observation] = self.client.start_as_current_observation(
            trace_context={"trace_id": trace_id_for(run_label, receipt_id)},
            name=name,
            as_type="span",
            input=input,
            metadata={"receipt_id": receipt_id, "run_label": run_label},
        )
        return cm

    def span(self, name: str, input: Any = None) -> AbstractContextManager[Observation]:
        cm: AbstractContextManager[Observation] = self.client.start_as_current_observation(
            name=name, as_type="span", input=input
        )
        return cm

    def generation(
        self, name: str, model: str, input: Any, **fields: Any
    ) -> AbstractContextManager[Observation]:
        cm: AbstractContextManager[Observation] = self.client.start_as_current_observation(
            name=name, as_type="generation", model=model, input=input, **fields
        )
        return cm

    def score(
        self, run_label: str, receipt_id: str, name: str, value: float, comment: str | None = None
    ) -> None:
        self.client.create_score(
            name=name,
            value=value,
            trace_id=trace_id_for(run_label, receipt_id),
            comment=comment,
            data_type="NUMERIC",
        )

    def flush(self, timeout_s: float = 5.0) -> None:
        self.client.flush()


class _GuardedObservation:
    def __init__(self, inner: Observation, owner: GuardedTracer) -> None:
        self._inner = inner
        self._owner = owner

    def update(self, **fields: Any) -> None:
        if not self._owner.enabled:
            return
        try:
            self._inner.update(**fields)
        except Exception as exc:
            self._owner.fail(exc)


class GuardedTracer:
    """Wraps a tracer so that no tracer error can stop or change a run."""

    def __init__(self, inner: Tracer) -> None:
        self._inner: Tracer = inner
        self._warned = False

    @property
    def enabled(self) -> bool:
        return self._inner.enabled

    @property
    def inner(self) -> Tracer:
        return self._inner

    def fail(self, exc: BaseException) -> None:
        if not self._warned:
            warnings.warn(
                f"tracing disabled for the rest of the run: {type(exc).__name__}: {exc}",
                TracingWarning,
                stacklevel=3,
            )
            self._warned = True
        self._inner = NoopTracer()

    @contextmanager
    def _guard(
        self, factory: Callable[[], AbstractContextManager[Observation]]
    ) -> Iterator[Observation]:
        try:
            cm = factory()
            observation = cm.__enter__()
        except Exception as exc:
            self.fail(exc)
            yield _NOOP_OBSERVATION
            return
        try:
            yield _GuardedObservation(observation, self)
        except BaseException as body_exc:
            try:
                cm.__exit__(type(body_exc), body_exc, body_exc.__traceback__)
            except Exception as exc:
                self.fail(exc)
            raise
        else:
            try:
                cm.__exit__(None, None, None)
            except Exception as exc:
                self.fail(exc)

    def receipt_trace(
        self, receipt_id: str, run_label: str, input: Any, name: str = "validate-receipt"
    ) -> AbstractContextManager[Observation]:
        return self._guard(lambda: self._inner.receipt_trace(receipt_id, run_label, input, name))

    def span(self, name: str, input: Any = None) -> AbstractContextManager[Observation]:
        return self._guard(lambda: self._inner.span(name, input))

    def generation(
        self, name: str, model: str, input: Any, **fields: Any
    ) -> AbstractContextManager[Observation]:
        return self._guard(lambda: self._inner.generation(name, model, input, **fields))

    def score(
        self, run_label: str, receipt_id: str, name: str, value: float, comment: str | None = None
    ) -> None:
        if not self._inner.enabled:
            return
        try:
            self._inner.score(run_label, receipt_id, name, value, comment)
        except Exception as exc:
            self.fail(exc)

    def flush(self, timeout_s: float = 5.0) -> None:
        if not self._inner.enabled:
            return
        ok = _bounded(lambda: self._inner.flush(timeout_s), timeout_s)
        if not ok:
            warnings.warn(
                f"tracer flush did not finish within {timeout_s}s; some traces may be missing",
                TracingWarning,
                stacklevel=2,
            )


def _bounded(fn: Callable[[], object], timeout_s: float) -> bool:
    """Run fn in a daemon thread; return True if it finished without error in time."""
    outcome: dict[str, bool] = {}

    def run() -> None:
        try:
            fn()
            outcome["ok"] = True
        except Exception:
            outcome["ok"] = False

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    thread.join(timeout_s)
    return outcome.get("ok", False)


def make_tracer(
    env: Mapping[str, str] | None = None, disabled: bool = False, timeout_s: float = 3.0
) -> GuardedTracer:
    """Langfuse if keys are present and the server answers in time; otherwise no-op."""
    if disabled:
        return GuardedTracer(NoopTracer())
    env = os.environ if env is None else env
    public, secret = env.get("LANGFUSE_PUBLIC_KEY"), env.get("LANGFUSE_SECRET_KEY")
    if not public or not secret:
        warnings.warn("Langfuse keys not set: tracing disabled", TracingWarning, stacklevel=2)
        return GuardedTracer(NoopTracer())
    from langfuse import Langfuse

    client = Langfuse(
        public_key=public,
        secret_key=secret,
        host=env.get("LANGFUSE_HOST") or None,
        timeout=int(timeout_s),
    )
    reachable: dict[str, bool] = {}
    finished = _bounded(lambda: reachable.update(ok=bool(client.auth_check())), timeout_s)
    if not finished or not reachable.get("ok"):
        warnings.warn("Langfuse unreachable: tracing disabled", TracingWarning, stacklevel=2)
        return GuardedTracer(NoopTracer())
    return GuardedTracer(LangfuseTracer(client))
