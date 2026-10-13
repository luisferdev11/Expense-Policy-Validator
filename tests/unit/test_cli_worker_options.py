"""`--cap-usd`, `--classifier` and `--simulated-latency-ms` on `epv serve` and `epv worker`."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from expense_validator.adapters.sqlite_store import SqliteStore
from expense_validator.app import cli
from expense_validator.app import composition as composition_module
from expense_validator.app.composition import build_worker
from expense_validator.domain.models import ClassifierRequest


def options(*argv: str) -> cli.WorkerOptions:
    args = cli.build_parser().parse_args(list(argv))
    return cli.worker_options(args)


@pytest.mark.parametrize("command", ["serve", "worker"])
def test_the_cap_defaults_to_one_dollar_and_parses_a_decimal(command: str) -> None:
    assert options(command).cap_usd == 1.00
    assert options(command, "--cap-usd", "0.25").cap_usd == 0.25


@pytest.mark.parametrize("command", ["serve", "worker"])
def test_a_negative_cap_is_rejected_by_the_parser(
    command: str, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit):
        options(command, "--cap-usd", "-1")
    assert "cap-usd" in capsys.readouterr().err


@pytest.mark.parametrize("command", ["serve", "worker"])
def test_the_classifier_and_the_simulated_latency_parse(command: str) -> None:
    default = options(command)
    assert (default.classifier, default.simulated_latency_ms) == ("openrouter", 0)
    chosen = options(command, "--classifier", "simulated", "--simulated-latency-ms", "1500")
    assert (chosen.classifier, chosen.simulated_latency_ms) == ("simulated", 1500)
    with pytest.raises(SystemExit):
        options(command, "--classifier", "gpt")
    with pytest.raises(SystemExit):
        options(command, "--simulated-latency-ms", "-5")


@pytest.mark.parametrize("command", ["serve", "worker"])
def test_the_shadow_is_off_by_default_and_takes_a_jev_name_and_its_own_cap(
    command: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("EPV_SHADOW", raising=False)
    default = options(command)
    assert (default.shadow, default.shadow_cap_usd) == (None, 0.25)
    chosen = options(command, "--shadow", "jev-hybrid", "--shadow-cap-usd", "0.05")
    assert (chosen.shadow, chosen.shadow_cap_usd) == ("jev-hybrid", 0.05)
    assert options(command, "--shadow", "jev-1.13").shadow == "jev-1.13"


@pytest.mark.parametrize("command", ["serve", "worker"])
def test_a_shadow_that_could_decide_is_refused(command: str) -> None:
    with pytest.raises(SystemExit):
        options(command, "--shadow", "gpt-oss-120b")  # only the jev classifiers are shadows
    with pytest.raises(SystemExit):
        options(command, "--shadow-cap-usd", "-1")


def test_the_environment_variable_sets_the_shadow_when_the_flag_is_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("EPV_SHADOW", "jev-1.13")
    assert options("worker").shadow == "jev-1.13"
    assert options("worker", "--shadow", "jev-hybrid").shadow == "jev-hybrid"  # the flag wins


def test_an_unknown_value_in_the_environment_is_refused_with_the_accepted_ones(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("EPV_SHADOW", "gpt-9")
    with pytest.raises(SystemExit, match=r"jev-1\.13, jev-hybrid"):
        options("worker")


def test_the_shadow_is_not_a_key_of_the_pipeline_configuration() -> None:
    """Shadow mode must not change `config/pipeline.yaml`: its hash is stamped into every result."""
    from expense_validator.adapters.config_files import PIPELINE_FILE

    assert "shadow" not in PIPELINE_FILE.read_text(encoding="utf-8").lower()


class Billing:
    """A fake OpenRouter transport that bills `cost` for every call."""

    def __init__(self, cost: float) -> None:
        self.cost = cost
        self.calls = 0

    def __call__(self, payload: dict[str, Any]) -> tuple[dict[str, Any], str]:
        self.calls += 1
        answer = {
            "category": "office_supplies",
            "confidence": 0.9,
            "subtype": "none",
            "recipient_kind": "none",
            "recipient_name": None,
        }
        body = {
            "id": f"gen-{self.calls}",
            "provider": "Fake",
            "choices": [{"message": {"content": json.dumps(answer)}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "cost": self.cost},
        }
        return body, json.dumps(body)


def test_the_cap_reaches_the_classifier_and_refuses_once_it_is_billed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(composition_module, "sync_prompt_links", lambda name, tracer, offline: {})
    store = SqliteStore(tmp_path / "epv.sqlite3")
    worker = build_worker(store, no_trace=True, cap_usd=0.25)
    classifier: Any = worker.classifier
    assert classifier.cap_usd == 0.25
    transport = Billing(0.25)
    classifier._transport = transport
    classifier.raw_dir = tmp_path / "raw"

    def request(text: str) -> ClassifierRequest:
        return ClassifierRequest(description_clean=text, merchant_name="M", mcc=5943)

    first = classifier.classify("L1", request("A line the committed cache has never seen"))
    second = classifier.classify("L2", request("Another line the cache has never seen"))
    assert first.status == "classified"
    assert (second.status, second.unclassified_reason) == ("unclassified", "budget_refused")
    assert transport.calls == 1
