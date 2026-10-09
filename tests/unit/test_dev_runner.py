"""Dev-set experiment runner (T012, research R4). Fake transport, no network."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from eval.experiments.run_dev import RegistrationError, check_registration, run_variant
from expense_validator.adapters.classification_cache import ClassificationCache
from expense_validator.adapters.openrouter.classifier import OpenRouterClassifier
from expense_validator.adapters.openrouter.models import PINS
from tests.fakes import RecordingTracer

ITEMS = [
    {"item_id": "DEV-001", "description": "Glass  of wine", "language": "en",
     "merchant_name": "Bistro", "mcc": 5812, "category": "alcohol", "restricted": True,
     "subtype": "none", "recipient_kind": "none", "recipient_name": None},
    {"item_id": "DEV-002", "description": "Club sandwich", "language": "en",
     "merchant_name": "Diner", "mcc": 5812, "category": "food_beverage", "restricted": False,
     "subtype": "none", "recipient_kind": "none", "recipient_name": None},
]  # fmt: skip


class Fake:
    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, payload: dict[str, Any]) -> tuple[dict[str, Any], str]:
        self.calls += 1
        text = payload["messages"][1]["content"]
        category = "alcohol" if "wine" in text else "food_beverage"
        content = json.dumps(
            {
                "category": category,
                "confidence": 0.9,
                "subtype": "none",
                "recipient_kind": "none",
                "recipient_name": None,
            }
        )
        body = {
            "id": f"gen-{self.calls}",
            "choices": [{"message": {"content": content}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 5, "completion_tokens": 5, "cost": 0.00001},
        }
        return body, json.dumps(body)


def plan(tmp_path: Path, approved: bool, data: str) -> Path:
    path = tmp_path / "plan.yaml"
    entry = {"id": "E14", "approved_by": "Luis" if approved else None, "data": data}
    path.write_text(yaml.safe_dump({"experiments": [entry]}), encoding="utf-8")
    return path


def test_refuses_without_approval_or_on_a_hash_mismatch(tmp_path: Path) -> None:
    with pytest.raises(RegistrationError, match="approved"):
        check_registration("E14", plan(tmp_path, False, "abc"), "abc")
    with pytest.raises(RegistrationError, match="hash"):
        check_registration("E14", plan(tmp_path, True, "abc"), "def")
    with pytest.raises(RegistrationError, match="E99"):
        check_registration("E99", plan(tmp_path, True, "abc"), "abc")
    assert check_registration("E14", plan(tmp_path, True, "abc"), "abc")["id"] == "E14"


def classifier(tmp_path: Path, fake: Fake, offline: bool = False) -> OpenRouterClassifier:
    return OpenRouterClassifier(
        ClassificationCache(tmp_path / "cache.jsonl"),
        RecordingTracer(),
        transport=fake,
        offline=offline,
        raw_dir=tmp_path / "raw",
        pin=PINS["gpt-oss-20b"],
    )


def test_one_row_per_item_with_every_field_and_one_trace_each(tmp_path: Path) -> None:
    tracer = RecordingTracer()
    clf = classifier(tmp_path, Fake())
    rows = run_variant("E14", "gpt-oss-20b", ITEMS, clf, tracer, tmp_path / "out.jsonl", "t")
    assert [r["item_id"] for r in rows] == ["DEV-001", "DEV-002"]
    fields = {
        "item_id", "variant", "model_id", "prompt_version", "status", "category", "restricted",
        "confidence", "subtype", "recipient_kind", "recipient_name", "raw_content",
        "request_id", "cost_usd", "cache_hit", "translation",
    }  # fmt: skip
    assert set(rows[0]) == fields
    assert rows[0]["category"] == "alcohol" and rows[0]["raw_content"].startswith("{")
    assert len(tracer.named("classify-dev-item")) == 2
    assert (tmp_path / "out.jsonl").exists()


def test_offline_replay_is_identical(tmp_path: Path) -> None:
    online = classifier(tmp_path, Fake())
    first = run_variant("E14", "v", ITEMS, online, RecordingTracer(), tmp_path / "a.jsonl", "t")
    online.cache.save()
    fake = Fake()
    offline = classifier(tmp_path, fake, offline=True)
    run_variant("E14", "v", ITEMS, offline, RecordingTracer(), tmp_path / "b.jsonl", "t")
    assert fake.calls == 0
    strip = [{k: v for k, v in r.items() if k != "cache_hit"} for r in first]
    again = [json.loads(x) for x in (tmp_path / "b.jsonl").read_text().splitlines()]
    assert [{k: v for k, v in r.items() if k != "cache_hit"} for r in again] == strip
