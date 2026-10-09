"""OpenRouter adapter with a fake transport: pin, cost, cap, failures, tracing (T027)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from expense_validator.adapters.classification_cache import ClassificationCache
from expense_validator.adapters.openrouter.classifier import (
    ENDPOINT,
    MODEL_ID,
    OpenRouterClassifier,
)
from expense_validator.adapters.openrouter.prompt import PROMPT_VERSION
from expense_validator.domain.models import ClassifierRequest
from tests.fakes import RecordingTracer

REQ = ClassifierRequest(description_clean="Arnold Palmer", merchant_name="Diner", mcc=5812)
ANSWER = {
    "category": "food_beverage",
    "confidence": 0.92,
    "subtype": "none",
    "recipient_kind": "none",
    "recipient_name": None,
}


class FakeTransport:
    def __init__(self, content: str | None = None, cost: float = 0.0002, fail: bool = False):
        self.content = json.dumps(ANSWER) if content is None else content
        self.cost = cost
        self.fail = fail
        self.payloads: list[dict[str, Any]] = []

    def __call__(self, payload: dict[str, Any]) -> tuple[dict[str, Any], str]:
        self.payloads.append(payload)
        if self.fail:
            raise ConnectionError("gateway down")
        body = {
            "id": f"gen-test-{len(self.payloads)}",
            "provider": "DeepInfra",
            "choices": [
                {
                    "message": {"content": self.content, "reasoning": "It is iced tea."},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 600, "completion_tokens": 40, "cost": self.cost},
        }
        return body, json.dumps(body)


def make(
    tmp_path: Path, transport: FakeTransport, **kw: Any
) -> tuple[OpenRouterClassifier, RecordingTracer]:
    tracer = RecordingTracer()
    clf = OpenRouterClassifier(
        cache=ClassificationCache(tmp_path / "c.jsonl"),
        tracer=tracer,
        transport=transport,
        raw_dir=tmp_path / "raw",
        **kw,
    )
    return clf, tracer


def test_request_is_pinned_and_deterministic(tmp_path: Path) -> None:
    transport = FakeTransport()
    clf, _ = make(tmp_path, transport)
    clf.classify("L1", REQ)
    (payload,) = transport.payloads
    assert payload["model"] == MODEL_ID == "openai/gpt-oss-120b"
    assert payload["temperature"] == 0
    assert payload["response_format"]["json_schema"]["strict"] is True
    provider = payload["extra_body"]["provider"]
    assert provider["order"] == [ENDPOINT] == ["deepinfra/bf16"]
    assert provider["allow_fallbacks"] is False
    assert provider["require_parameters"] is True


def test_success_records_cost_and_request_id(tmp_path: Path) -> None:
    clf, _ = make(tmp_path, FakeTransport(cost=0.0003))
    c = clf.classify("L1", REQ)
    assert c.status == "classified"
    assert c.category == "food_beverage"
    assert c.restricted is False
    assert c.source.request_id == "gen-test-1"
    assert c.source.cost_usd == 0.0003
    assert c.source.prompt_version == PROMPT_VERSION
    assert c.source.cache_hit is False
    assert clf.run_spend_usd == 0.0003


def test_second_call_is_a_cache_hit_without_a_generation(tmp_path: Path) -> None:
    transport = FakeTransport()
    clf, tracer = make(tmp_path, transport)
    clf.classify("L1", REQ)
    again = clf.classify("L9", REQ)
    assert again.source.cache_hit is True
    assert again.line_id == "L9"
    assert len(transport.payloads) == 1
    assert len(tracer.named("classify-item")) == 1


def test_generation_carries_the_contract_fields(tmp_path: Path) -> None:
    clf, tracer = make(tmp_path, FakeTransport())
    clf.classify("L1", REQ)
    (gen,) = tracer.named("classify-item")
    assert gen.kind == "generation"
    assert gen.fields["model"] == MODEL_ID
    assert gen.fields["input"][1]["content"].startswith("Item: Arnold Palmer")
    final = {k: v for u in gen.updates for k, v in u.items()}
    assert final["usage_details"] == {"input": 600, "output": 40}
    assert final["cost_details"] == {"total": 0.0002}
    assert final["metadata"]["request_id"] == "gen-test-1"
    assert final["metadata"]["reasoning"] == "It is iced tea."


def test_gateway_error_is_unclassified(tmp_path: Path) -> None:
    clf, _ = make(tmp_path, FakeTransport(fail=True))
    c = clf.classify("L1", REQ)
    assert (c.status, c.unclassified_reason) == ("unclassified", "gateway_error")


def test_schema_violation_is_unclassified_and_cached_as_the_raw_answer(tmp_path: Path) -> None:
    transport = FakeTransport(content='{"category": "beer", "confidence": 1}')
    clf, _ = make(tmp_path, transport)
    c = clf.classify("L1", REQ)
    assert (c.status, c.unclassified_reason) == ("unclassified", "schema_violation")
    again = clf.classify("L2", REQ)
    assert (again.status, again.unclassified_reason) == ("unclassified", "schema_violation")
    assert again.source.cache_hit is True
    assert len(transport.payloads) == 1
    (row,) = clf.cache._rows.values()
    assert row.content == '{"category": "beer", "confidence": 1}'


def test_cached_raw_answers_are_parsed_on_read(tmp_path: Path) -> None:
    clf, _ = make(tmp_path, FakeTransport())
    clf.classify("L1", REQ)
    clf.cache.save()
    reread = ClassificationCache(tmp_path / "c.jsonl")
    offline = OpenRouterClassifier(reread, RecordingTracer(), offline=True)
    c = offline.classify("L1", REQ)
    assert (c.status, c.category, c.source.cache_hit) == ("classified", "food_beverage", True)


def test_cap_refuses_the_call(tmp_path: Path) -> None:
    transport = FakeTransport(cost=0.6)
    clf, _ = make(tmp_path, transport, cap_usd=1.0)
    clf.classify("L1", REQ)
    clf.classify("L2", REQ.model_copy(update={"description_clean": "Tea"}))
    third = clf.classify("L3", REQ.model_copy(update={"description_clean": "Coffee"}))
    assert (third.status, third.unclassified_reason) == ("unclassified", "budget_refused")
    assert len(transport.payloads) == 2


def test_offline_never_calls_the_transport(tmp_path: Path) -> None:
    transport = FakeTransport()
    clf, _ = make(tmp_path, transport, offline=True)
    c = clf.classify("L1", REQ)
    assert (c.status, c.unclassified_reason) == ("unclassified", "offline_cache_miss")
    assert transport.payloads == []


def test_raw_body_is_kept_locally(tmp_path: Path) -> None:
    clf, _ = make(tmp_path, FakeTransport())
    clf.classify("L1", REQ)
    assert (tmp_path / "raw" / "gen-test-1.json").exists()


@pytest.mark.parametrize("attr", ["name", "model_id", "provider_endpoint", "prompt_version"])
def test_exposes_run_metadata(tmp_path: Path, attr: str) -> None:
    clf, _ = make(tmp_path, FakeTransport())
    assert getattr(clf, attr)
