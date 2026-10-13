"""Prompt sync for cls-v2 and dec-v1 (spec 007, T011). No Langfuse server: a fake client."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from expense_validator.adapters.openrouter.prompt_sync import (
    CHAT_PROMPT,
    CONFIG,
    DECISION_CONFIG,
    DECISION_TEXT,
    sync_decision_prompt,
    sync_prompt,
)
from expense_validator.adapters.tracing import (
    GuardedTracer,
    LangfuseTracer,
    NoopTracer,
    TracingWarning,
)


class FakeClient:
    """Stores prompts by (name, label); `get_prompt` raises until one is created."""

    def __init__(self, stored: dict[tuple[str, str], Any] | None = None, fail: bool = False):
        self.stored = stored or {}
        self.created: list[dict[str, Any]] = []
        self.fail = fail

    def get_prompt(self, name: str, label: str, type: str, cache_ttl_seconds: int) -> Any:
        if self.fail:
            raise ConnectionError("langfuse down")
        return self.stored[(name, label)]

    def create_prompt(self, **fields: Any) -> None:
        if self.fail:
            raise ConnectionError("langfuse down")
        self.created.append(fields)
        self.stored[(fields["name"], fields["labels"][0])] = SimpleNamespace(
            prompt=fields["prompt"], config=fields["config"], name=fields["name"]
        )


def tracer_over(client: FakeClient) -> GuardedTracer:
    return GuardedTracer(LangfuseTracer(client))


@pytest.mark.parametrize("sync", [sync_prompt, sync_decision_prompt])
def test_a_no_op_tracer_gets_no_prompt_link(sync: Any) -> None:
    assert sync(GuardedTracer(NoopTracer())) is None


@pytest.mark.parametrize("sync", [sync_prompt, sync_decision_prompt])
def test_a_failing_client_only_warns(sync: Any) -> None:
    with pytest.warns(TracingWarning, match="could not sync prompt"):
        assert sync(tracer_over(FakeClient(fail=True))) is None


def test_the_decision_prompt_is_created_under_its_name_and_label() -> None:
    client = FakeClient()
    link = sync_decision_prompt(tracer_over(client))
    (created,) = client.created
    assert created["name"] == "classify-item-decision"
    assert created["labels"] == ["dec-v1"]
    assert created["type"] == "text"
    assert created["prompt"] == DECISION_TEXT
    assert created["config"] == DECISION_CONFIG
    assert created["config"]["endpoint"] == "/api/alpha/decisions"
    assert link.name == "classify-item-decision"
    assert "Classify what the item IS" in DECISION_TEXT


def test_an_identical_stored_prompt_creates_no_new_version() -> None:
    stored = SimpleNamespace(prompt=DECISION_TEXT, config=DECISION_CONFIG)
    client = FakeClient({("classify-item-decision", "dec-v1"): stored})
    assert sync_decision_prompt(tracer_over(client)) is stored
    assert client.created == []


def test_a_changed_stored_prompt_creates_a_new_version() -> None:
    stored = SimpleNamespace(prompt="old text", config=DECISION_CONFIG)
    client = FakeClient({("classify-item-decision", "dec-v1"): stored})
    sync_decision_prompt(tracer_over(client))
    assert len(client.created) == 1


def test_the_chat_prompt_sync_is_unchanged() -> None:
    client = FakeClient()
    sync_prompt(tracer_over(client))
    (created,) = client.created
    assert created["name"] == "classify-item-chat"
    assert created["labels"] == ["cls-v2"]
    assert created["type"] == "chat"
    assert created["prompt"] == CHAT_PROMPT
    assert created["config"] == CONFIG
