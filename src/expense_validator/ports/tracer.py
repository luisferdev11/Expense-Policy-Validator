"""The Tracer port (CLAUDE.md rule 11, contracts/tracing.md).

Implementations live in adapters/tracing.py: Langfuse, a no-op tracer, and a guard that swaps a
failing tracer for the no-op one, so tracing never gates a run.
"""

from __future__ import annotations

from contextlib import AbstractContextManager
from typing import Any, Protocol, runtime_checkable


class Observation(Protocol):
    def update(self, **fields: Any) -> None: ...


@runtime_checkable
class Tracer(Protocol):
    @property
    def enabled(self) -> bool: ...

    def receipt_trace(
        self, receipt_id: str, run_label: str, input: Any, name: str = "validate-receipt"
    ) -> AbstractContextManager[Observation]: ...

    def span(self, name: str, input: Any = None) -> AbstractContextManager[Observation]: ...

    def generation(
        self, name: str, model: str, input: Any, **fields: Any
    ) -> AbstractContextManager[Observation]: ...

    def score(
        self, run_label: str, receipt_id: str, name: str, value: float, comment: str | None = None
    ) -> None:
        """Attach a numeric score to the trace of one receipt in one run. Best effort."""
        ...

    def flush(self, timeout_s: float = 5.0) -> None: ...
