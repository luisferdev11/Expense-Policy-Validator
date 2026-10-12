"""The decision adapter (jev) with a fake transport and the JSONL cache (spec 007, T009).

No billed call and no network: the transport is a fake, and the real httpx transport runs over
`httpx.MockTransport`. After spec 006 merges, the cache fixture gets a second parametrisation over
the table adapter.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from expense_validator.adapters.classification_cache import ClassificationCache, cache_key
from expense_validator.adapters.openrouter.decision_classifier import (
    URL,
    DecisionClassifier,
    httpx_transport,
)
from expense_validator.adapters.openrouter.decision_prompt import decision_cache_key
from expense_validator.adapters.openrouter.prompt import PROMPT_VERSION
from expense_validator.domain.models import ClassifierRequest
from tests.fakes import RecordingTracer

REQ = ClassifierRequest(description_clean="Arnold Palmer", merchant_name="Diner", mcc=5812)
GOOD = {
    "answers": {
        "category": {
            "choice": "food_beverage",
            "probabilities": {"food_beverage": 0.97, "alcohol": 0.03},
            "confidence": 0.9,
        }
    }
}


class FakeTransport:
    def __init__(
        self, answer: dict[str, Any] | None = None, cost: float = 0.0002, fail: bool = False
    ):
        self.answer = GOOD if answer is None else answer
        self.cost = cost
        self.fail = fail
        self.payloads: list[dict[str, Any]] = []

    def __call__(self, payload: dict[str, Any]) -> tuple[dict[str, Any], str]:
        self.payloads.append(payload)
        if self.fail:
            raise ConnectionError("gateway down")
        body = {
            "id": f"dec-test-{len(self.payloads)}",
            "provider": "typesafe",
            **self.answer,
            "usage": {"input_tokens": 700, "output_tokens": 12, "cost": self.cost},
        }
        return body, json.dumps(body)


def make(
    tmp_path: Path, transport: FakeTransport, **kw: Any
) -> tuple[DecisionClassifier, RecordingTracer]:
    tracer = RecordingTracer()
    clf = DecisionClassifier(
        cache=ClassificationCache(tmp_path / "c.jsonl"),
        tracer=tracer,
        transport=transport,
        raw_dir=tmp_path / "raw",
        **kw,
    )
    return clf, tracer


def test_a_miss_makes_one_call_one_generation_and_caches_the_literal_body(tmp_path: Path) -> None:
    transport = FakeTransport()
    clf, tracer = make(tmp_path, transport)
    c = clf.classify("L1", REQ)
    (payload,) = transport.payloads
    assert payload["model"] == "typesafe/jev-1.13"
    assert payload["state"] == {"item": "Arnold Palmer", "merchant": "Diner", "mcc": "5812"}
    assert (c.status, c.category, c.restricted, c.confidence) == (
        "classified",
        "food_beverage",
        False,
        0.97,
    )
    assert (c.subtype, c.recipient_kind, c.recipient_name) == ("none", "none", None)
    assert c.source.classifier == "openrouter-decision"
    assert c.source.model_id == "typesafe/jev-1.13"
    assert c.source.prompt_version == "dec-v1"
    assert c.source.request_id == "dec-test-1"
    assert c.source.cost_usd == 0.0002
    assert (c.source.prompt_tokens, c.source.completion_tokens) == (700, 12)
    assert c.source.served_by == "typesafe"
    assert c.source.cache_hit is False
    assert clf.calls_made == 1
    assert clf.run_spend_usd == 0.0002
    assert clf.last_latency_s is not None
    assert len(tracer.named("classify-item")) == 1
    entry = clf.cache.get(c.source.cache_key)
    assert entry is not None
    assert json.loads(entry.content or "")["id"] == "dec-test-1"  # the literal body
    assert entry.reasoning == "confidence_source=top_probability"


def test_the_generation_carries_the_contract_fields(tmp_path: Path) -> None:
    clf, tracer = make(tmp_path, FakeTransport(), prompt_link="LINK")
    c = clf.classify("L1", REQ)
    (gen,) = tracer.named("classify-item")
    assert gen.kind == "generation"
    assert gen.fields["model"] == "typesafe/jev-1.13"
    assert gen.fields["input"]["questions"]["category"]["type"] == "choice"
    assert gen.fields["model_parameters"] == {
        "endpoint": "/api/alpha/decisions",
        "kind": "decision",
        "provider_endpoint": "openrouter",
    }
    assert gen.fields["prompt"] == "LINK"
    assert gen.fields["metadata"] == {
        "prompt_version": "dec-v1",
        "cache_key": c.source.cache_key,
    }
    final = {k: v for u in gen.updates for k, v in u.items()}
    assert final["output"]["choice"] == "food_beverage"
    assert final["usage_details"] == {"input": 700, "output": 12}
    assert final["cost_details"] == {"total": 0.0002}
    assert final["metadata"] == {
        "request_id": "dec-test-1",
        "served_by": "typesafe",
        "confidence_source": "top_probability",
    }


def test_a_hit_makes_no_call_no_generation_and_an_identical_classification(
    tmp_path: Path,
) -> None:
    transport = FakeTransport()
    clf, tracer = make(tmp_path, transport)
    first = clf.classify("L1", REQ)
    again = clf.classify("L1", REQ)
    assert len(transport.payloads) == 1
    assert len(tracer.named("classify-item")) == 1
    assert again.source.cache_hit is True
    assert clf.cache_hits == 1
    assert clf.last_latency_s is None
    assert again.model_copy(update={"source": first.source}) == first
    assert again.source == first.source.model_copy(update={"cache_hit": True})


def test_a_replay_from_a_saved_cache_in_offline_mode_is_identical(tmp_path: Path) -> None:
    clf, _ = make(tmp_path, FakeTransport())
    first = clf.classify("L1", REQ)
    clf.cache.save()  # type: ignore[attr-defined]
    offline = DecisionClassifier(
        ClassificationCache(tmp_path / "c.jsonl"), RecordingTracer(), offline=True
    )
    again = offline.classify("L1", REQ)
    assert again.category == first.category and again.confidence == first.confidence
    assert again.source.cache_hit is True


def test_the_key_differs_from_the_chat_key_for_the_same_request(tmp_path: Path) -> None:
    clf, _ = make(tmp_path, FakeTransport())
    c = clf.classify("L1", REQ)
    assert c.source.cache_key == decision_cache_key(REQ, "typesafe/jev-1.13", "openrouter")
    assert c.source.cache_key != cache_key(REQ, "typesafe/jev-1.13", "openrouter", PROMPT_VERSION)
    assert c.source.cache_key != cache_key(REQ, "openai/gpt-oss-120b", "openrouter", PROMPT_VERSION)


def test_the_confidence_falls_back_to_the_reported_one(tmp_path: Path) -> None:
    answer = {"answers": {"category": {"choice": "alcohol", "confidence": 0.81}}}
    clf, _ = make(tmp_path, FakeTransport(answer))
    c = clf.classify("L1", REQ)
    assert (c.category, c.restricted, c.confidence) == ("alcohol", True, 0.81)
    entry = clf.cache.get(c.source.cache_key)
    assert entry is not None and entry.reasoning == "confidence_source=confidence"


def test_a_transport_error_is_a_gateway_error_and_is_not_cached(tmp_path: Path) -> None:
    transport = FakeTransport(fail=True)
    clf, tracer = make(tmp_path, transport)
    c = clf.classify("L1", REQ)
    assert (c.status, c.unclassified_reason) == ("unclassified", "gateway_error")
    assert clf.cache.get(c.source.cache_key) is None
    assert clf.calls_made == 0
    (gen,) = tracer.named("classify-item")
    assert gen.updates[-1] == {"level": "ERROR", "status_message": "ConnectionError"}
    transport.fail = False
    assert clf.classify("L1", REQ).status == "classified"  # retried, nothing was cached


def test_an_offline_miss_makes_no_call(tmp_path: Path) -> None:
    transport = FakeTransport()
    clf, _ = make(tmp_path, transport, offline=True)
    c = clf.classify("L1", REQ)
    assert (c.status, c.unclassified_reason) == ("unclassified", "offline_cache_miss")
    assert transport.payloads == []


def test_the_cap_counts_what_this_process_billed(tmp_path: Path) -> None:
    transport = FakeTransport(cost=0.6)
    clf, _ = make(tmp_path, transport, cap_usd=1.0)
    clf.classify("L1", REQ)
    clf.classify("L2", REQ.model_copy(update={"description_clean": "Tea"}))
    third = clf.classify("L3", REQ.model_copy(update={"description_clean": "Coffee"}))
    assert (third.status, third.unclassified_reason) == ("unclassified", "budget_refused")
    assert len(transport.payloads) == 2
    # a cached answer is still served at the cap, and costs nothing
    assert clf.classify("L1", REQ).source.cache_hit is True


@pytest.mark.parametrize(
    "answer",
    [
        {"answers": {"category": {"choice": "moonbeams", "confidence": 0.9}}},
        {"answers": {"category": {"choice": "alcohol", "confidence": 3}}},
        {"answers": {}},
        {"nothing": True},
    ],
)
def test_a_bad_choice_is_a_schema_violation_live_and_on_replay(
    tmp_path: Path, answer: dict[str, Any]
) -> None:
    transport = FakeTransport(answer)
    clf, tracer = make(tmp_path, transport)
    first = clf.classify("L1", REQ)
    assert (first.status, first.unclassified_reason) == ("unclassified", "schema_violation")
    again = clf.classify("L2", REQ)
    assert (again.status, again.unclassified_reason) == ("unclassified", "schema_violation")
    assert again.source.cache_hit is True
    assert len(transport.payloads) == 1
    (gen,) = tracer.named("classify-item")
    assert gen.updates[-1]["level"] == "WARNING"
    assert gen.updates[-1]["status_message"].startswith("schema_violation")


def test_the_raw_body_is_kept_locally(tmp_path: Path) -> None:
    clf, _ = make(tmp_path, FakeTransport())
    clf.classify("L1", REQ)
    assert (tmp_path / "raw" / "dec-test-1.json").exists()


@pytest.mark.parametrize("attr", ["name", "model_id", "provider_endpoint", "prompt_version"])
def test_exposes_run_metadata(tmp_path: Path, attr: str) -> None:
    clf, _ = make(tmp_path, FakeTransport())
    assert getattr(clf, attr)


def test_a_missing_key_is_a_gateway_error_not_a_crash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    clf = DecisionClassifier(
        ClassificationCache(tmp_path / "c.jsonl"), RecordingTracer(), raw_dir=tmp_path / "raw"
    )
    c = clf.classify("L1", REQ)
    assert (c.status, c.unclassified_reason) == ("unclassified", "gateway_error")


# The real transport, over httpx's mock transport: retries and errors, with no network.


def mock_client(handler: Any) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_the_transport_posts_the_payload_with_a_bearer_key_and_returns_the_body() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=GOOD)

    send = httpx_transport("sk-test-not-a-key", mock_client(handler), sleep=lambda s: None)
    body, text = send({"model": "m", "state": {}})
    assert body == GOOD and json.loads(text) == GOOD
    (request,) = seen
    assert str(request.url) == URL
    assert request.headers["authorization"] == "Bearer sk-test-not-a-key"
    assert json.loads(request.content) == {"model": "m", "state": {}}


def test_the_transport_retries_429_502_and_503_with_backoff() -> None:
    statuses = iter([429, 502, 503, 200])
    waits: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        status = next(statuses)
        return httpx.Response(status, json=GOOD if status == 200 else {"error": "x"})

    send = httpx_transport("k", mock_client(handler), sleep=waits.append)
    body, _ = send({})
    assert body == GOOD
    assert waits == [2, 4, 8]  # min(30, 2**attempt) for attempts 1 to 3


def test_the_transport_gives_up_after_six_attempts() -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(429, json={})

    waits: list[float] = []
    send = httpx_transport("k", mock_client(handler), sleep=waits.append)
    with pytest.raises(RuntimeError, match="HTTP 429"):
        send({})
    assert len(calls) == 6
    assert waits == [2, 4, 8, 16, 30]  # capped at 30


@pytest.mark.parametrize("status", [400, 401, 404, 500])
def test_the_transport_raises_on_any_other_error_status_without_retrying(status: int) -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(status, json={})

    send = httpx_transport("k", mock_client(handler), sleep=lambda s: None)
    with pytest.raises(RuntimeError, match=f"HTTP {status}"):
        send({})
    assert len(calls) == 1


def test_the_error_message_never_contains_the_key() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={})

    send = httpx_transport("sk-secret-value", mock_client(handler), sleep=lambda s: None)
    with pytest.raises(RuntimeError) as info:
        send({})
    assert "sk-secret-value" not in str(info.value)
