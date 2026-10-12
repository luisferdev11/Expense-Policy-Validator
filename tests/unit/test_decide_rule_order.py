"""The guards come before superiority, and a superior challenger wins outright (spec 007, US3).

Synthetic items and rows only: no dev labels. The two functions under test are `e14` (labels kept as
registered, so the committed outcome is byte-identical) and `judge` with `strict=True` (E16's
registered order: exclusion, A6/A9 guard, restricted guard, superiority, non-inferiority).
"""

from __future__ import annotations

from typing import Any

from eval.experiments.decide import e14, judge

N = 60
A6A9 = 6  # items 0..5 exercise A6/A9
REFERENCE = "gpt-oss-120b"


def items() -> list[dict[str, Any]]:
    return [
        {
            "item_id": f"DEV-{i:03d}",
            "category": "food_beverage" if i % 5 else "alcohol",
            "restricted": i % 5 == 0,
            "subtype": "none",
            "recipient_kind": "none",
            "recipient_name": None,
            "a6a9": i < A6A9,
            "language": "en",
        }
        for i in range(N)
    ]


def rows(
    wrong: set[int] = frozenset(),  # type: ignore[assignment]
    a6a9_wrong: int = 0,
    cost: float = 0.00004,
    restricted_missed: set[int] = frozenset(),  # type: ignore[assignment]
) -> list[dict[str, Any]]:
    """A prediction per item: `wrong` get another category, the first `a6a9_wrong` A6/A9 items get
    a wrong subtype, and `restricted_missed` items (alcohol) are predicted unrestricted."""
    out = []
    for item in items():
        i = int(item["item_id"].split("-")[1])
        category = item["category"]
        if i in wrong:
            category = "household_goods"
        restricted = category == "alcohol"
        if i in restricted_missed:
            category, restricted = "food_beverage", False
        out.append(
            {
                "item_id": item["item_id"],
                "status": "classified",
                "category": category,
                "restricted": restricted,
                "confidence": 0.9,
                "subtype": "event_ticket" if i < a6a9_wrong else "none",
                "recipient_kind": "none",
                "cost_usd": cost,
            }
        )
    return out


REFERENCE_WRONG = {i for i in range(1, 15) if i % 5}  # 12 unrestricted items


def reference_rows() -> list[dict[str, Any]]:
    """The reference gets 12 unrestricted items wrong (so its restricted F1 is 1), and no A6/A9
    item wrong."""
    return rows(wrong=REFERENCE_WRONG, cost=0.00004)


def test_a_superior_challenger_that_fails_the_a6a9_guard_cannot_win() -> None:
    # 60/60 against 48/60 (b=12, c=0, p = 0.0005), but 6 A6/A9 items wrong against 0
    challenger = rows(a6a9_wrong=6, cost=0.000005)
    results = {REFERENCE: reference_rows(), "jev-like": challenger}
    for outcome in (e14(results, items()), judge(results, items(), strict=True)):
        by = {v["variant"]: v for v in outcome["variants"]}
        assert by["jev-like"]["a6a9_wrong"] == 6
        assert by["jev-like"]["status"] == "fails_a6a9_guard"
        assert outcome["winner"] == REFERENCE


def test_a_superior_challenger_that_costs_more_wins_outright() -> None:
    results = {REFERENCE: reference_rows(), "better": rows(cost=0.0004)}
    for outcome in (e14(results, items()), judge(results, items(), strict=True)):
        by = {v["variant"]: v for v in outcome["variants"]}
        assert by["better"]["status"] == "superior"
        assert outcome["winner"] == "better"
        assert "better" not in outcome["why_others_lost"]
        assert REFERENCE in outcome["why_others_lost"]


def test_among_several_superior_challengers_the_cheaper_wins() -> None:
    results = {
        REFERENCE: reference_rows(),
        "dear": rows(cost=0.0004),
        "cheap": rows(cost=0.00001),
    }
    for outcome in (e14(results, items()), judge(results, items(), strict=True)):
        assert outcome["winner"] == "cheap"
        assert outcome["why_others_lost"]["dear"] == "more expensive"


def test_with_no_superior_challenger_the_cheapest_of_the_reference_and_non_inferior_wins() -> None:
    results = {
        REFERENCE: rows(wrong=REFERENCE_WRONG, cost=0.00004),
        "same-cheaper": rows(wrong=REFERENCE_WRONG, cost=0.00001),
        "same-dearer": rows(wrong=REFERENCE_WRONG, cost=0.0004),
    }
    for outcome in (e14(results, items()), judge(results, items(), strict=True)):
        by = {v["variant"]: v for v in outcome["variants"]}
        assert by["same-cheaper"]["status"] == "non_inferior"
        assert outcome["winner"] == "same-cheaper"
        assert outcome["why_others_lost"][REFERENCE] == "more expensive"


def test_the_restricted_guard_fails_a_superior_challenger() -> None:
    # 58/60 against 48/60 (b=12, c=2, p = 0.0129), but two restricted items are predicted
    # unrestricted: restricted F1 0.909 against the reference's 1.0.
    challenger = rows(restricted_missed={0, 15}, cost=0.000005)
    results = {REFERENCE: reference_rows(), "misses-restricted": challenger}
    for outcome in (e14(results, items()), judge(results, items(), strict=True)):
        by = {v["variant"]: v for v in outcome["variants"]}
        assert by["misses-restricted"]["restricted_f1"] < by[REFERENCE]["restricted_f1"] - 0.01
        assert by["misses-restricted"]["status"] == "fails_restricted_guard"
        assert outcome["winner"] == REFERENCE


def test_strict_order_labels_a_guard_failure_even_when_not_superior_or_non_inferior() -> None:
    # Two more items wrong than the reference makes it "worse" on accuracy, but a guard failure is
    # reported as the guard under E16's registered order. E14 keeps its registered labels.
    challenger = rows(wrong=set(range(1, 40)), a6a9_wrong=6)
    results = {REFERENCE: reference_rows(), "weak": challenger}
    strict = {v["variant"]: v for v in judge(results, items(), strict=True)["variants"]}
    legacy = {v["variant"]: v for v in e14(results, items())["variants"]}
    assert strict["weak"]["status"] == "fails_a6a9_guard"
    assert legacy["weak"]["status"] == "worse"


def test_schema_violations_exclude_before_any_guard() -> None:
    bad = rows(a6a9_wrong=6)
    for r in bad[:4]:
        r.update(status="unclassified", category=None, restricted=None, confidence=None)
        r["unclassified_reason"] = "schema_violation"
    results = {REFERENCE: reference_rows(), "invalid": bad}
    for outcome in (e14(results, items()), judge(results, items(), strict=True)):
        by = {v["variant"]: v for v in outcome["variants"]}
        assert by["invalid"]["status"] == "excluded"
