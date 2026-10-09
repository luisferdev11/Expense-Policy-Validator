"""The registered iteration 2 rules, applied mechanically (T018). Synthetic predictions only."""

from __future__ import annotations

import json
from typing import Any

import pytest

from eval.experiments.decide import IncompleteRunError, e5, e7, e14, e15, ret

N = 60


def items(n: int = N, a6a9: int = 6, non_english: int = 20) -> list[dict[str, Any]]:
    return [
        {
            "item_id": f"DEV-{i:03d}",
            "category": "food_beverage",
            "restricted": False,
            "subtype": "none",
            "recipient_kind": "none",
            "recipient_name": None,
            "a6a9": i < a6a9,
            "language": "es" if i < non_english else "en",
        }
        for i in range(n)
    ]


def answer(category: str, subtype: Any = "none") -> str:
    return json.dumps(
        {
            "category": category,
            "confidence": 0.9,
            "subtype": subtype,
            "recipient_kind": "none",
            "recipient_name": None,
        }
    )


def rows(
    wrong: set[int],
    cost: float = 0.00004,
    confidence: float = 0.9,
    n: int = N,
    schema_bad: set[int] = frozenset(),  # type: ignore[assignment]
) -> list[dict[str, Any]]:
    out = []
    for i in range(n):
        bad = i in schema_bad
        category = None if bad else ("alcohol" if i in wrong else "food_beverage")
        out.append(
            {
                "item_id": f"DEV-{i:03d}",
                "status": "unclassified" if bad else "classified",
                "category": category,
                "restricted": None if bad else category == "alcohol",
                "confidence": None if bad else confidence,
                "subtype": "none",
                "recipient_kind": "none",
                "raw_content": answer(category or "food_beverage", None if bad else "none"),
                "cost_usd": cost,
            }
        )
    return out  # fmt: skip


def test_e14_cheaper_equivalent_challenger_wins() -> None:
    results = {
        "gpt-oss-120b": rows({1, 2}, cost=0.00004),
        "gpt-oss-20b": rows({1, 2}, cost=0.00001),
        "qwen3.5-9b": rows(set(range(20)), cost=0.000005),
    }
    out = e14(results, items())
    assert out["winner"] == "gpt-oss-20b"
    by = {v["variant"]: v for v in out["variants"]}
    assert by["gpt-oss-20b"]["status"] == "non_inferior"
    assert by["qwen3.5-9b"]["status"] == "worse"
    assert by["gpt-oss-120b"]["accuracy"]["n"] == N


def test_e14_keeps_the_reference_when_nothing_qualifies() -> None:
    results = {"gpt-oss-120b": rows(set()), "gemma-3-12b": rows(set(range(10)), cost=0.0)}
    assert e14(results, items())["winner"] == "gpt-oss-120b"


def test_e14_excludes_more_than_2_percent_schema_violations() -> None:
    results = {"gpt-oss-120b": rows(set()), "gpt-oss-20b": rows(set(), 0.0, schema_bad={1, 2})}
    by = {v["variant"]: v for v in e14(results, items())["variants"]}
    assert by["gpt-oss-20b"]["status"] == "excluded"


def test_e14_refuses_to_decide_while_a_run_has_gateway_errors() -> None:
    broken = rows(set())
    broken[5] = {**broken[5], "status": "unclassified", "unclassified_reason": "gateway_error"}
    with pytest.raises(IncompleteRunError, match="gpt-oss-20b"):
        e14({"gpt-oss-120b": rows(set()), "gpt-oss-20b": broken}, items())


def test_e14_counts_only_schema_violations_toward_exclusion() -> None:
    bad = rows(set(), 0.0, schema_bad={1, 2})
    for r in bad:
        if r["status"] == "unclassified":
            r["unclassified_reason"] = "schema_violation"
    by = {
        v["variant"]: v
        for v in e14({"gpt-oss-120b": rows(set()), "gpt-oss-20b": bad}, items())["variants"]
    }
    assert by["gpt-oss-20b"]["schema_violations"]["value"] == 2 / N
    assert by["gpt-oss-20b"]["status"] == "excluded"


def test_e14_a6a9_guard() -> None:
    results = {"gpt-oss-120b": rows(set()), "gpt-oss-20b": rows({0, 1, 2}, cost=0.0)}
    by = {v["variant"]: v for v in e14(results, items())["variants"]}
    assert by["gpt-oss-20b"]["status"] in {"worse", "fails_a6a9_guard"}


def test_e15_adopts_null_as_none_only_when_it_fixes_and_breaks_nothing() -> None:
    base = rows(set(), schema_bad={3})
    out = e15({"gpt-oss-120b": base}, items())
    assert out["winner"] == "null_as_none"
    assert out["fixed"] == 1 and out["broken"] == 0
    clean = e15({"gpt-oss-120b": rows(set())}, items())
    assert clean["winner"] == "strict" and clean["observed"] == 0


def test_e5_keeps_the_original_without_evidence() -> None:
    out = e5(rows({1}), rows({1}), items())
    assert out["winner"] == "original"
    assert out["n"] == 20


def test_e7_picks_lower_brier_and_a_threshold_by_the_rule() -> None:
    winner = rows({1, 2}, confidence=0.9)
    for r in winner:
        if r["item_id"] in {"DEV-001", "DEV-002"}:
            r["confidence"] = 0.3
    out = e7(winner, winner, rows({1, 2, 3}), items())
    assert out["winner"] == "self_reported"
    assert out["threshold"] == 0.9


def test_ret_keeps_the_trigger_map_when_identical() -> None:
    assert ret({"cases": 45, "differences": 0})["winner"] == "trigger_map"
    assert ret({"cases": 45, "differences": 2})["winner"] == "investigate"
