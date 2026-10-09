"""Prompt cls-v2 and its strict schema (T023, FR-005, FR-006, FR-009)."""

import json
from pathlib import Path
from typing import Any

import pytest

from expense_validator.classification.prompt import (
    PROMPT_VERSION,
    RESPONSE_FORMAT_STRICT,
    SCHEMA,
    ParseError,
    parse,
)

CONTRACT = (
    Path(__file__).resolve().parents[2]
    / "specs"
    / "001-mvp-end-to-end"
    / "contracts"
    / "classifier-output-cls-v2.schema.json"
)


def answer(**overrides: Any) -> str:
    base = {
        "category": "food_beverage",
        "confidence": 0.9,
        "subtype": "none",
        "recipient_kind": "none",
        "recipient_name": None,
    }
    return json.dumps(base | overrides)


def test_version() -> None:
    assert PROMPT_VERSION == "cls-v2"


def test_schema_equals_the_contract() -> None:
    contract = json.loads(CONTRACT.read_text())
    for key in ("$schema", "title", "description"):
        contract.pop(key)
    assert contract == SCHEMA
    assert RESPONSE_FORMAT_STRICT["json_schema"]["strict"] is True


def test_valid_answer_parses() -> None:
    parsed = parse(
        answer(
            category="other",
            subtype="event_ticket",
            recipient_kind="client_or_prospect",
            recipient_name="  Ana   Ruiz ",
        )
    )
    assert parsed.category == "other"
    assert parsed.subtype == "event_ticket"
    assert parsed.recipient_name == "Ana Ruiz"


@pytest.mark.parametrize(
    "content",
    [
        None,
        "",
        "not json",
        answer(category="beer"),
        answer(confidence=1.5),
        answer(confidence=-0.1),
        answer(subtype="event_ticket"),
        answer(recipient_kind="friend"),
        json.dumps({"category": "food_beverage", "confidence": 0.9}),
        answer(extra="x"),
        "```json\n" + answer() + "\n```",
    ],
)
def test_schema_violations_are_rejected(content: str | None) -> None:
    with pytest.raises(ParseError):
        parse(content)
