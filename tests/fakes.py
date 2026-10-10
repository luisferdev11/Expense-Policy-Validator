"""Test doubles: a recording tracer and a fake classifier. No network."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from expense_validator.domain.models import Classification, ClassifierRequest
from tests.factories import cls, unclassified


@dataclass
class Recorded:
    kind: str
    name: str
    fields: dict[str, Any]
    updates: list[dict[str, Any]] = field(default_factory=list)

    def update(self, **fields: Any) -> None:
        self.updates.append(fields)


class RecordingTracer:
    """Implements the Tracer protocol and keeps every observation in memory."""

    enabled = True

    def __init__(self) -> None:
        self.observations: list[Recorded] = []
        self.scores: list[dict[str, Any]] = []

    @contextmanager
    def _record(self, kind: str, name: str, **fields: Any) -> Iterator[Recorded]:
        obs = Recorded(kind, name, fields)
        self.observations.append(obs)
        yield obs

    def receipt_trace(
        self, receipt_id: str, run_label: str, input: Any, name: str = "validate-receipt"
    ) -> Any:
        return self._record("trace", name, receipt_id=receipt_id, input=input)

    def span(self, name: str, input: Any = None) -> Any:
        return self._record("span", name, input=input)

    def generation(self, name: str, model: str, input: Any, **fields: Any) -> Any:
        return self._record("generation", name, model=model, input=input, **fields)

    def score(
        self, run_label: str, receipt_id: str, name: str, value: float, comment: str | None = None
    ) -> None:
        self.scores.append(
            {
                "run_label": run_label,
                "receipt_id": receipt_id,
                "name": name,
                "value": value,
                "comment": comment,
            }
        )

    def flush(self, timeout_s: float = 5.0) -> None:
        return None

    def named(self, name: str) -> list[Recorded]:
        return [o for o in self.observations if o.name == name]


class StepClock:
    """A controllable clock: each reading advances by `step`; `advance` jumps ahead."""

    def __init__(self, start: datetime | None = None, step: timedelta | None = None) -> None:
        self.now = start or datetime(2026, 10, 10, 12, 0, tzinfo=UTC)
        self.step = step if step is not None else timedelta(milliseconds=1)

    def __call__(self) -> datetime:
        current = self.now
        self.now += self.step
        return current

    def advance(self, by: timedelta) -> None:
        self.now += by


class SimulatedCrash(BaseException):
    """The process dies: not an `Exception`, so no stage handler may catch it."""


class BillingClassifier:
    """A classifier with an in-memory answer cache that counts billed calls.

    `cache` can be shared between instances to play the role of the cache file that survives a
    restart. `categories` maps a cleaned description to a category. `crash_after` raises
    `SimulatedCrash` when a billed call would be number `crash_after + 1`; `fail_with` raises it
    as an ordinary error; `on_classify` runs before every call (to interleave other actions).
    """

    name = "billing-fake"
    model_id = "fake-model"
    provider_endpoint = "none"
    prompt_version = "test"

    def __init__(
        self,
        categories: dict[str, str],
        cache: dict[tuple[str, str, int], Classification] | None = None,
        crash_after: int | None = None,
        fail_with: Exception | None = None,
        on_classify: Callable[[], None] | None = None,
        confidence: float = 0.99,
        recipients: dict[str, tuple[str, str | None]] | None = None,
        unclassified_reasons: dict[str, str] | None = None,
    ) -> None:
        self.categories = categories
        self.recipients = recipients or {}
        self.unclassified_reasons = unclassified_reasons or {}
        self.cache = cache if cache is not None else {}
        self.crash_after = crash_after
        self.fail_with = fail_with
        self.on_classify = on_classify
        self.confidence = confidence
        self.calls_made = 0
        self.cache_hits = 0

    def classify(self, line_id: str, request: ClassifierRequest) -> Classification:
        if self.on_classify is not None:
            self.on_classify()
        if self.fail_with is not None:
            raise self.fail_with
        reason = self.unclassified_reasons.get(request.description_clean)
        if reason is not None:  # like the real adapter, which returns instead of raising
            return unclassified(line_id, reason)
        key = (request.description_clean, request.merchant_name, request.mcc)
        found = self.cache.get(key)
        if found is None:
            if self.crash_after is not None and self.calls_made >= self.crash_after:
                raise SimulatedCrash
            self.calls_made += 1
            kind, name = self.recipients.get(request.description_clean, ("none", None))
            found = cls(
                line_id,
                self.categories[request.description_clean],
                self.confidence,
                recipient_kind=kind,
                recipient_name=name,
            )
            self.cache[key] = found
        else:
            self.cache_hits += 1
        return found.model_copy(update={"line_id": line_id})


class FakeClassifier:
    """Maps a cleaned description to a fixed Classification (line_id is rewritten)."""

    name = "fake"
    model_id = "fake-model"
    provider_endpoint = "none"
    prompt_version = "test"

    def __init__(self, by_description: dict[str, Classification]) -> None:
        self.by_description = by_description

    def classify(self, line_id: str, request: ClassifierRequest) -> Classification:
        found = self.by_description[request.description_clean]
        return found.model_copy(update={"line_id": line_id})
