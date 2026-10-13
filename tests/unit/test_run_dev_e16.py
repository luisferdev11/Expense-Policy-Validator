"""The E16 runner: registration gate, variants, the hybrid's committed side, rows, the repeat pass
(spec 007, T021). Fake transports only: no network and no billed call."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from eval.experiments import run_dev
from eval.experiments.run_dev import (
    E16_BUDGET_USD,
    RegistrationError,
    build_e16_classifier,
    check_registration,
    e14_detail_cache,
    e16_cap,
    e16_spend,
    repeat_subset_ids,
    run_repeat_pass,
    run_variant_e16,
)
from expense_validator.adapters.classification_cache import ClassificationCache
from expense_validator.adapters.hybrid_classifier import HybridClassifier
from expense_validator.adapters.openrouter.decision_classifier import DecisionClassifier
from expense_validator.paths import REPO_ROOT
from tests.fakes import RecordingTracer

ITEMS = [
    {"item_id": "DEV-001", "description": "Glass  of wine", "language": "en",
     "merchant_name": "Bistro", "mcc": 5812, "category": "alcohol", "restricted": True,
     "subtype": "none", "recipient_kind": "none", "recipient_name": None},
    {"item_id": "DEV-002", "description": "Club sandwich", "language": "en",
     "merchant_name": "Diner", "mcc": 5812, "category": "food_beverage", "restricted": False,
     "subtype": "none", "recipient_kind": "none", "recipient_name": None},
    {"item_id": "DEV-003", "description": "Mystery charge", "language": "en",
     "merchant_name": "Corner", "mcc": 5999, "category": "other", "restricted": False,
     "subtype": "none", "recipient_kind": "none", "recipient_name": None},
]  # fmt: skip
CONTRACT = REPO_ROOT / "specs" / "007-jev-classifier" / "contracts" / "e16-rule.md"
PLAN = REPO_ROOT / "explorations" / "research" / "experiments_plan.yaml"


def plan(tmp_path: Path, approved: bool, data: str = "abc") -> Path:
    path = tmp_path / "plan.yaml"
    entry = {"id": "E16", "approved_by": "Luis" if approved else None, "data": data}
    path.write_text(yaml.safe_dump({"iteration_2": [entry]}), encoding="utf-8")
    return path


def test_e16_is_refused_without_approval_and_runs_with_it(tmp_path: Path) -> None:
    with pytest.raises(RegistrationError, match="not approved"):
        check_registration("E16", plan(tmp_path, False), "abc")
    with pytest.raises(RegistrationError, match="hash"):
        check_registration("E16", plan(tmp_path, True), "different")
    assert check_registration("E16", plan(tmp_path, True), "abc")["id"] == "E16"


def test_the_committed_registration_is_the_text_of_the_approved_contract() -> None:
    block = CONTRACT.read_text(encoding="utf-8").split("```yaml", 1)[1].split("```", 1)[0]
    (contract,) = yaml.safe_load(block)
    registered = {e["id"]: e for e in yaml.safe_load(PLAN.read_text())["iteration_2"]}["E16"]
    assert registered["approved_by"] == "Luis"
    contract.pop("registered_at")
    registered = dict(registered)
    assert registered.pop("registered_at").startswith("2026-10-12")
    assert registered == contract
    # and it is registered on the frozen set the experiment will run on
    assert check_registration("E16", PLAN, registered["data"])["variants"] == [
        "jev-1.13",
        "jev-hybrid",
    ]


def test_the_variant_is_one_of_the_two_jev_variants(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(run_dev, "load_env", lambda: None)
    with pytest.raises(SystemExit, match=r"jev-1\.13, jev-hybrid"):
        run_dev.main(["--experiment", "E16", "--variant", "gpt-oss-20b"])
    with pytest.raises(SystemExit, match=r"jev-1\.13 variant"):
        run_dev.main(["--experiment", "E16", "--variant", "jev-hybrid", "--repeat-subset", "5"])


def jev_transport(
    changes: set[str] = frozenset(),  # type: ignore[assignment]
    cost: float = 0.00001,
) -> Any:
    state = {"calls": 0}

    def send(payload: dict[str, Any]) -> tuple[dict[str, Any], str]:
        state["calls"] += 1
        text = payload["state"]["item"].lower()
        choice = "alcohol" if "wine" in text else "food_beverage"
        if payload["state"]["item"] in changes:
            choice = "other"
        body = {
            "id": f"jev-{state['calls']}",
            "provider": "typesafe",
            "answers": {
                "category": {
                    "choice": choice,
                    "probabilities": {choice: 0.9},
                    "confidence": 0.8,
                }
            },
            "usage": {"input_tokens": 700, "output_tokens": 10, "cost": cost},
        }
        return body, json.dumps(body)

    send.state = state  # type: ignore[attr-defined]
    return send


def e14_rows(tmp_path: Path) -> Path:
    """The reference's committed rows for the first two items; the third has none."""

    def row(item_id: str, category: str, subtype: str, kind: str) -> dict[str, Any]:
        answer = {
            "category": category,
            "confidence": 0.9,
            "subtype": subtype,
            "recipient_kind": kind,
            "recipient_name": None,
        }
        return {
            "item_id": item_id,
            "raw_content": json.dumps(answer),
            "request_id": f"e14-{item_id}",
            "cost_usd": 0.00004,
            "served_by": "DeepInfra",
        }

    path = tmp_path / "gpt-oss-120b.jsonl"
    rows = [
        row("DEV-001", "alcohol", "none", "client_or_prospect"),
        row("DEV-002", "food_beverage", "none", "none"),
    ]
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return path


def hybrid_over(tmp_path: Path, transport: Any, offline: bool = False) -> HybridClassifier:
    detail = e14_detail_cache(ITEMS, e14_rows(tmp_path), tmp_path / "absent.jsonl")
    clf = build_e16_classifier(
        "jev-hybrid",
        RecordingTracer(),
        ITEMS,
        offline=offline,
        cap_usd=0.10,
        jev_cache=ClassificationCache(tmp_path / "jev.jsonl"),
        detail_cache=detail,
        jev_transport=transport,
        raw_dir=tmp_path / "raw",
    )
    assert isinstance(clf, HybridClassifier)
    return clf


def test_the_hybrid_reads_the_committed_e14_answers_and_never_bills_the_detail_side(
    tmp_path: Path,
) -> None:
    transport = jev_transport()
    clf = hybrid_over(tmp_path, transport)
    rows = run_variant_e16(
        "jev-hybrid", ITEMS, clf, RecordingTracer(), tmp_path / "hybrid.jsonl", "E16-test"
    )
    by = {r["item_id"]: r for r in rows}
    assert by["DEV-001"]["status"] == "classified"
    assert by["DEV-001"]["recipient_kind"] == "client_or_prospect"  # the detail side's answer
    assert by["DEV-001"]["detail_raw_content"] is not None
    assert by["DEV-002"]["status"] == "classified"
    # an item with no committed answer is an offline miss, never a gpt-oss call
    assert by["DEV-003"]["unclassified_reason"] == "offline_cache_miss"
    assert clf.detail_source.calls_made == 0
    assert clf.category_source.calls_made == 3  # jev answered the three items
    assert by["DEV-001"]["cost_usd"] == pytest.approx(0.00005)  # jev + the E14 answer's cost


def test_the_jev_variant_row_has_every_field_and_the_latency_only_on_a_billed_call(
    tmp_path: Path,
) -> None:
    jev_cache = ClassificationCache(tmp_path / "jev.jsonl")
    tracer = RecordingTracer()
    clf = build_e16_classifier(
        "jev-1.13",
        tracer,
        ITEMS,
        offline=False,
        cap_usd=0.10,
        jev_cache=jev_cache,
        jev_transport=jev_transport(),
        raw_dir=tmp_path / "raw",
    )
    assert isinstance(clf, DecisionClassifier)
    first = run_variant_e16("jev-1.13", ITEMS, clf, tracer, tmp_path / "a.jsonl", "E16-jev")
    fields = {
        "item_id", "variant", "model_id", "prompt_version", "status", "category", "restricted",
        "confidence", "top_probability", "reported_confidence", "confidence_source", "subtype",
        "recipient_kind", "recipient_name", "raw_content", "detail_raw_content", "request_id",
        "cost_usd", "latency_s", "cache_hit", "unclassified_reason", "served_by",
    }  # fmt: skip
    assert set(first[0]) == fields
    row = first[0]
    assert (row["category"], row["top_probability"], row["reported_confidence"]) == (
        "alcohol",
        0.9,
        0.8,
    )
    assert row["confidence"] == 0.9 and row["confidence_source"] == "top_probability"
    assert row["subtype"] == "none" and row["recipient_kind"] == "none"
    assert row["latency_s"] is not None and row["cache_hit"] is False
    assert len(tracer.named("classify-dev-item")) == 3
    second = run_variant_e16("jev-1.13", ITEMS, clf, tracer, tmp_path / "b.jsonl", "E16-jev")
    assert all(r["cache_hit"] is True and r["latency_s"] is None for r in second)
    assert [r["category"] for r in second] == [r["category"] for r in first]


def test_an_unknown_variant_is_refused_by_the_builder(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="E16 variants"):
        build_e16_classifier(
            "gpt-oss-20b",
            RecordingTracer(),
            ITEMS,
            offline=True,
            cap_usd=0.1,
            jev_cache=ClassificationCache(tmp_path / "j.jsonl"),
        )


def test_the_budget_is_what_remains_of_usd_0_10(tmp_path: Path) -> None:
    assert e16_cap(tmp_path / "none") == pytest.approx(E16_BUDGET_USD)
    cache = ClassificationCache(tmp_path / "jev-1.13.jsonl")
    clf = build_e16_classifier(
        "jev-1.13",
        RecordingTracer(),
        ITEMS,
        offline=False,
        cap_usd=0.10,
        jev_cache=cache,
        jev_transport=jev_transport(cost=0.01),
        raw_dir=tmp_path / "raw",
    )
    run_variant_e16("jev-1.13", ITEMS, clf, RecordingTracer(), tmp_path / "o.jsonl", "E16")
    cache.save()
    assert e16_spend(tmp_path) == pytest.approx(0.03)
    assert e16_cap(tmp_path) == pytest.approx(0.07)


def test_the_repeat_subset_is_a_fixed_random_sample() -> None:
    items = [{"item_id": f"DEV-{i:03d}"} for i in range(130)]
    ids = repeat_subset_ids(items, 20)
    assert len(ids) == len(set(ids)) == 20
    assert ids == repeat_subset_ids(items, 20) == sorted(ids)
    assert ids != [f"DEV-{i:03d}" for i in range(20)]  # not simply the first twenty
    assert repeat_subset_ids(items[:5], 20) == sorted(i["item_id"] for i in items[:5])


def test_the_repeat_pass_bypasses_the_first_cache_and_counts_what_changed(tmp_path: Path) -> None:
    first = [
        {"item_id": "DEV-001", "category": "alcohol"},
        {"item_id": "DEV-002", "category": "food_beverage"},
        {"item_id": "DEV-003", "category": "food_beverage"},
    ]
    transport = jev_transport(changes={"Mystery charge"})
    rows = run_repeat_pass(
        ITEMS,
        3,
        first,
        RecordingTracer(),
        tmp_path / "repeat.jsonl",
        offline=False,
        cap_usd=0.10,
        cache_path=tmp_path / "jev-1.13.repeat.jsonl",
        jev_transport=transport,
        raw_dir=tmp_path / "raw",
    )
    assert transport.state["calls"] == 3  # every item asked again, no first-pass cache involved
    assert {r["item_id"]: r["changed"] for r in rows} == {
        "DEV-001": False,
        "DEV-002": False,
        "DEV-003": True,  # the first pass said food_beverage, the second says other
    }
    on_disk = [json.loads(x) for x in (tmp_path / "repeat.jsonl").read_text().splitlines()]
    assert on_disk == rows
    assert e16_spend(tmp_path) == pytest.approx(0.00003)  # the repeat's calls count in the budget
