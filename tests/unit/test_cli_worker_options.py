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
