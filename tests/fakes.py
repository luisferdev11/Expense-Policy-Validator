"""Test doubles: a recording tracer and a fake classifier. No network."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

from expense_validator.domain.models import Classification, ClassifierRequest


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

    def flush(self, timeout_s: float = 5.0) -> None:
        return None

    def named(self, name: str) -> list[Recorded]:
        return [o for o in self.observations if o.name == name]


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
