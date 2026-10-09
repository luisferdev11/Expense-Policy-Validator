"""Model pins for E14 through the pipeline's own OpenRouter adapter (T006, research R1)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from expense_validator.adapters.classification_cache import ClassificationCache, cache_key
from expense_validator.adapters.openrouter.classifier import OpenRouterClassifier
from expense_validator.adapters.openrouter.models import PINS, REFERENCE
from expense_validator.adapters.openrouter.prompt import PROMPT_VERSION
from expense_validator.domain.models import ClassifierRequest
from expense_validator.paths import CLASSIFICATIONS_FILE
from tests.fakes import RecordingTracer

REQ = ClassifierRequest(description_clean="Club sandwich", merchant_name="Diner", mcc=5812)
ANSWER = json.dumps(
    {
        "category": "food_beverage",
        "confidence": 0.9,
        "subtype": "none",
        "recipient_kind": "none",
        "recipient_name": None,
    }
)


class Fake:
    def __init__(self) -> None:
        self.payloads: list[dict[str, Any]] = []

    def __call__(self, payload: dict[str, Any]) -> tuple[dict[str, Any], str]:
        self.payloads.append(payload)
        body = {
            "id": f"gen-{len(self.payloads)}",
            "choices": [{"message": {"content": ANSWER}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "cost": 0.00001},
        }
        return body, json.dumps(body)


def payload_for(name: str, tmp_path: Path) -> dict[str, Any]:
    fake = Fake()
    clf = OpenRouterClassifier(
        ClassificationCache(tmp_path / f"{name}.jsonl"),
        RecordingTracer(),
        transport=fake,
        raw_dir=tmp_path / "raw",
        pin=PINS[name],
    )
    clf.classify("L1", REQ)
    return fake.payloads[0]


def test_the_four_candidates_and_the_reference() -> None:
    assert set(PINS) == {"gpt-oss-120b", "gpt-oss-20b", "qwen3.5-9b", "gemma-3-12b"}
    assert REFERENCE is PINS["gpt-oss-120b"]


@pytest.mark.parametrize("name", ["gpt-oss-120b", "gpt-oss-20b", "qwen3.5-9b", "gemma-3-12b"])
def test_each_pin_sends_its_model_endpoint_and_temperature(name: str, tmp_path: Path) -> None:
    payload = payload_for(name, tmp_path)
    assert payload["model"] == PINS[name].model_id
    assert payload["temperature"] == 0
    assert payload["extra_body"]["provider"]["order"] == ["deepinfra/bf16"]
    assert payload["extra_body"]["provider"]["allow_fallbacks"] is False


def test_reasoning_settings_per_pin(tmp_path: Path) -> None:
    assert payload_for("gpt-oss-120b", tmp_path)["extra_body"]["reasoning"] == {"effort": "low"}
    assert payload_for("gpt-oss-20b", tmp_path)["extra_body"]["reasoning"] == {"effort": "low"}
    assert payload_for("qwen3.5-9b", tmp_path)["extra_body"]["reasoning"] == {"enabled": False}
    assert "reasoning" not in payload_for("gemma-3-12b", tmp_path)["extra_body"]


def test_cache_keys_differ_per_pin_and_the_reference_keys_are_unchanged() -> None:
    keys = {cache_key(REQ, p.model_id, p.endpoint, PROMPT_VERSION) for p in PINS.values()}
    assert len(keys) == 4
    committed = [json.loads(x) for x in CLASSIFICATIONS_FILE.read_text().splitlines() if x]
    assert all(row["model_id"] == REFERENCE.model_id for row in committed)
    assert all(row["provider_endpoint"] == REFERENCE.endpoint for row in committed)
