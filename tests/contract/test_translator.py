"""Translator for E5: prompt tr-v1, cached, traced, never gating (T008, research R6)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from expense_validator.adapters.openrouter.translator import PROMPT_VERSION, Translator
from tests.fakes import RecordingTracer


class Fake:
    def __init__(self, text: str = "  Pickled vegetables in sake lees \n", fail: bool = False):
        self.text, self.fail = text, fail
        self.payloads: list[dict[str, Any]] = []

    def __call__(self, payload: dict[str, Any]) -> tuple[dict[str, Any], str]:
        self.payloads.append(payload)
        if self.fail:
            raise ConnectionError("down")
        body = {
            "id": f"gen-tr-{len(self.payloads)}",
            "choices": [{"message": {"content": self.text}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 20, "completion_tokens": 8, "cost": 0.00001},
        }
        return body, json.dumps(body)


def make(tmp_path: Path, fake: Fake) -> tuple[Translator, RecordingTracer]:
    tracer = RecordingTracer()
    return Translator(
        tmp_path / "tr.jsonl", tracer, transport=fake, raw_dir=tmp_path / "raw"
    ), tracer


def test_version_and_plain_stripped_output(tmp_path: Path) -> None:
    assert PROMPT_VERSION == "tr-v1"
    translator, _ = make(tmp_path, Fake())
    assert translator.translate("酒粕漬け", "ja") == "Pickled vegetables in sake lees"


def test_cached_second_call_and_one_generation(tmp_path: Path) -> None:
    fake = Fake()
    translator, tracer = make(tmp_path, fake)
    translator.translate("酒粕漬け", "ja")
    translator.translate("酒粕漬け", "ja")
    assert len(fake.payloads) == 1
    assert len(tracer.named("translate-item")) == 1
    translator.save()
    again, _ = make(tmp_path, Fake(fail=True))
    assert again.translate("酒粕漬け", "ja") == "Pickled vegetables in sake lees"


def test_english_is_never_sent(tmp_path: Path) -> None:
    fake = Fake()
    translator, _ = make(tmp_path, fake)
    assert translator.translate("Club sandwich", "en") == "Club sandwich"
    assert fake.payloads == []


def test_gateway_error_returns_none(tmp_path: Path) -> None:
    translator, _ = make(tmp_path, Fake(fail=True))
    assert translator.translate("Cerveza", "es") is None


def test_offline_miss_returns_none_without_calling(tmp_path: Path) -> None:
    fake = Fake()
    translator = Translator(tmp_path / "t.jsonl", RecordingTracer(), transport=fake, offline=True)
    assert translator.translate("Cerveza", "es") is None
    assert fake.payloads == []
