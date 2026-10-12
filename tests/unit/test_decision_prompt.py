"""Prompt dec-v1 and its strict parser (spec 007, T007)."""

from __future__ import annotations

import json
from typing import Any

import pytest

from expense_validator.adapters.classification_cache import cache_key
from expense_validator.adapters.openrouter.decision_prompt import (
    DECISION_INSTRUCTIONS,
    DECISION_PROMPT_VERSION,
    decision_cache_key,
    decision_payload,
    parse_decision,
)
from expense_validator.adapters.openrouter.prompt import PROMPT_VERSION, ParseError
from expense_validator.domain.models import ClassifierRequest
from expense_validator.domain.taxonomy import CATEGORIES
from expense_validator.paths import REPO_ROOT

FIXTURE = REPO_ROOT / "tests" / "fixtures" / "dec_v1_payload.json"


def fixture_items() -> list[dict[str, Any]]:
    document = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert document["prompt_version"] == "dec-v1"
    items: list[dict[str, Any]] = document["items"]
    return items


def request_of(item: dict[str, Any]) -> ClassifierRequest:
    return ClassifierRequest(
        description_clean=item["description_clean"],
        merchant_name=item["merchant_name"],
        mcc=item["mcc"],
    )


def test_the_moved_payload_equals_the_exploration_payload_for_three_items() -> None:
    items = fixture_items()
    assert len(items) == 3
    for item in items:
        assert decision_payload(request_of(item)) == item["payload"]


def test_the_payload_carries_the_instructions_and_every_category() -> None:
    payload = decision_payload(ClassifierRequest(description_clean="x", merchant_name="m", mcc=1))
    question = payload["questions"]["category"]
    assert question["type"] == "choice"
    assert question["instructions"] == DECISION_INSTRUCTIONS
    assert list(question["criteria"]) == list(CATEGORIES)
    assert payload["state"] == {"item": "x", "merchant": "m", "mcc": "1"}
    assert DECISION_PROMPT_VERSION == "dec-v1"


def test_the_cache_key_differs_from_the_chat_key_and_follows_the_payload() -> None:
    request = ClassifierRequest(description_clean="beer", merchant_name="Pub", mcc=5813)
    key = decision_cache_key(request, "typesafe/jev-1.13", "openrouter")
    chat = cache_key(request, "typesafe/jev-1.13", "openrouter", PROMPT_VERSION)
    assert key != chat
    assert key == decision_cache_key(request, "typesafe/jev-1.13", "openrouter")
    other = ClassifierRequest(description_clean="beer", merchant_name="Pub", mcc=5814)
    assert key != decision_cache_key(other, "typesafe/jev-1.13", "openrouter")


def body(**answer: Any) -> str:
    return json.dumps({"id": "gen-1", "answers": {"category": answer}})


def test_the_top_probability_is_the_confidence() -> None:
    parsed = parse_decision(
        body(choice="alcohol", probabilities={"alcohol": 0.93, "other": 0.07}, confidence=0.5)
    )
    assert (parsed.category, parsed.confidence, parsed.confidence_source) == (
        "alcohol",
        0.93,
        "top_probability",
    )


def test_the_reported_confidence_is_the_fallback() -> None:
    for answer in (
        {"choice": "alcohol", "confidence": 0.8},
        {"choice": "alcohol", "probabilities": {"other": 1.0}, "confidence": 0.8},
        {"choice": "alcohol", "probabilities": {"alcohol": 1.2}, "confidence": 0.8},
    ):
        parsed = parse_decision(body(**answer))
        assert (parsed.confidence, parsed.confidence_source) == (0.8, "confidence")


@pytest.mark.parametrize(
    "content",
    [
        body(choice="moonbeams", confidence=0.9),
        body(choice=None, confidence=0.9),
        body(choice="alcohol", confidence=1.5),
        body(choice="alcohol", confidence=-0.1),
        body(choice="alcohol", confidence="high"),
        body(choice="alcohol", confidence=True),
        body(choice="alcohol"),
        json.dumps({"answers": {}}),
        json.dumps({"answers": {"category": "alcohol"}}),
        json.dumps({"id": "x"}),
        json.dumps([1, 2]),
        "not json",
        "",
        None,
    ],
)
def test_a_malformed_answer_is_a_parse_error(content: str | None) -> None:
    with pytest.raises(ParseError):
        parse_decision(content)
