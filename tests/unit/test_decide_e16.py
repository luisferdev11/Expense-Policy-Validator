"""E16 applied mechanically to synthetic rows (spec 007, T023): the rule of contracts/e16-rule.md,
the latency figures, the repeatability measure and E7's threshold procedure for a jev winner."""

from __future__ import annotations

from typing import Any

import pytest

from eval.experiments.decide import REFERENCE, e16, table
from tests.unit.test_decide_rule_order import items, reference_rows, rows

N = 60


def jev_rows(
    wrong: set[int] = frozenset(),  # type: ignore[assignment]
    a6a9_wrong: int = 0,
    cost: float = 0.00001,
    top: float = 0.95,
    reported: float = 0.9,
    low_top: set[int] = frozenset(),  # type: ignore[assignment]
    latency: float | None = None,
) -> list[dict[str, Any]]:
    out = rows(wrong=wrong, a6a9_wrong=a6a9_wrong, cost=cost)
    for i, r in enumerate(out):
        r["top_probability"] = 0.4 if i in low_top else top
        r["reported_confidence"] = reported
        r["confidence"] = r["top_probability"]
        r["confidence_source"] = "top_probability"
        r["latency_s"] = None if latency is None else latency + (i % 5) / 10
    return out


def results(**variants: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    names = {"jev_1_13": "jev-1.13", "jev_hybrid": "jev-hybrid"}
    return {REFERENCE: reference_rows(), **{names[k]: v for k, v in variants.items()}}


def test_the_rule_is_applied_in_the_registered_order() -> None:
    out = e16(
        results(
            jev_1_13=jev_rows(a6a9_wrong=6, latency=0.5),  # superior on accuracy, fails A6/A9
            jev_hybrid=jev_rows(cost=0.0004),  # superior and costs more: wins outright
        ),
        items(),
    )
    by = {v["variant"]: v for v in out["variants"]}
    assert by["jev-1.13"]["status"] == "fails_a6a9_guard"
    assert by["jev-hybrid"]["status"] == "superior"
    assert out["winner"] == "jev-hybrid"
    assert out["why_others_lost"]["jev-1.13"].startswith("more than 2 extra A6/A9")
    assert (
        out["why_others_lost"][REFERENCE] == "a superior challenger is chosen before the reference"
    )
    assert (out["id"], out["n"], out["reference"]) == ("E16", N, REFERENCE)


def test_the_bootstrap_uses_the_registered_seed() -> None:
    from eval.experiments.decide import judge
    from eval.stats import paired_bootstrap

    rs = results(jev_1_13=jev_rows(), jev_hybrid=jev_rows(cost=0.0004))
    out = e16(rs, items())
    seeded = judge(rs, items(), strict=True, seed=20261012)
    for mine, theirs in zip(out["variants"], seeded["variants"], strict=True):
        for key in ("variant", "status", "accuracy", "difference", "mcnemar"):
            assert mine.get(key) == theirs.get(key)
    ref = [int(r["category"] == i["category"]) for r, i in zip(rs[REFERENCE], items(), strict=True)]
    new = [
        int(r["category"] == i["category"]) for r, i in zip(rs["jev-1.13"], items(), strict=True)
    ]
    _, lo, hi = paired_bootstrap(new, ref, seed=20261012)
    by = {v["variant"]: v for v in out["variants"]}
    assert by["jev-1.13"]["difference"]["interval"] == [round(lo, 4), round(hi, 4)]


def test_a_jev_winner_gets_its_threshold_from_e7s_procedure_on_the_better_calibrated_source() -> (
    None
):
    # two wrong items, answered with a low top probability; the reported confidence is high for
    # every item, so the top probability has the lower Brier score
    winner = jev_rows(wrong={21, 22}, cost=0.0004, low_top={21, 22})
    out = e16(results(jev_1_13=jev_rows(a6a9_wrong=6, latency=0.5), jev_hybrid=winner), items())
    assert out["winner"] == "jev-hybrid"
    assert out["confidence_source"] == "top_probability"
    assert (
        out["sources"]["top_probability"]["brier"] < out["sources"]["reported_confidence"]["brier"]
    )
    assert set(out["sources"]["top_probability"]) == {
        "brier",
        "ece",
        "bins_with_10_items",
        "calibration_measurable",
    }
    assert (
        out["threshold"] == 0.95
    )  # the highest accuracy on the items kept, none correct sent away
    fires = out["fires_on_dev"]
    assert (fires["k"], fires["n"]) == (2, N)
    assert out["curve"]  # the coverage-accuracy curve, as E7 reports it


def test_a_threshold_of_zero_is_a_valid_outcome_when_every_answer_is_correct() -> None:
    out = e16(results(jev_1_13=jev_rows(a6a9_wrong=6), jev_hybrid=jev_rows(cost=0.0004)), items())
    assert out["winner"] == "jev-hybrid"
    assert out["threshold"] == 0.0
    assert (out["fires_on_dev"]["k"], out["fires_on_dev"]["n"]) == (0, N)


def test_when_the_reference_wins_there_is_no_jev_threshold() -> None:
    out = e16(results(jev_1_13=jev_rows(a6a9_wrong=6), jev_hybrid=jev_rows(a6a9_wrong=6)), items())
    assert out["winner"] == REFERENCE
    assert out["threshold"] is None and out["confidence_source"] is None
    assert out["fires_on_dev"] is None


def test_latency_median_and_p95_are_reported_per_variant_and_borrowed_by_the_hybrid() -> None:
    jev = jev_rows(latency=0.5)  # 0.5 to 0.9 in steps of 0.1, 12 of each
    out = e16(results(jev_1_13=jev, jev_hybrid=jev_rows(cost=0.0004)), items())
    by = {v["variant"]: v for v in out["variants"]}
    own = by["jev-1.13"]["latency_s"]
    assert (own["n"], own["median"], own["p95"]) == (60, 0.7, 0.9)
    assert own["measured_on"] == "jev-1.13"
    # the hybrid's rows came from the cache, so they carry no timing: it borrows the jev call's
    assert by["jev-hybrid"]["latency_s"]["measured_on"] == "jev-1.13"
    assert by["jev-hybrid"]["latency_s"]["median"] == 0.7
    assert by[REFERENCE]["latency_s"] is None  # E14 did not record latency


def test_a_tie_on_cost_goes_to_the_lower_median_latency() -> None:
    equal = {"cost": 0.00004}
    out = e16(
        results(
            jev_1_13=jev_rows(wrong=set(range(1, 15)) - {5, 10}, latency=0.9, **equal),
            jev_hybrid=jev_rows(wrong=set(range(1, 15)) - {5, 10}, latency=0.1, **equal),
        ),
        items(),
    )
    by = {v["variant"]: v for v in out["variants"]}
    assert by["jev-1.13"]["status"] == by["jev-hybrid"]["status"] == "non_inferior"
    assert by[REFERENCE]["cost_per_1000_usd"] == by["jev-1.13"]["cost_per_1000_usd"]
    assert out["winner"] == "jev-hybrid"  # same cost as the others, the lowest latency


def test_repeatability_is_reported_as_k_of_n_and_the_spend_includes_it() -> None:
    repeat = [{"item_id": f"DEV-{i:03d}", "changed": i < 3, "cost_usd": 0.00001} for i in range(20)]
    jev = jev_rows(latency=0.5, cost=0.00002)
    out = e16(results(jev_1_13=jev, jev_hybrid=jev_rows(cost=0.0004)), items(), repeat)
    rep = out["repeatability"]
    assert (rep["k"], rep["n"]) == (3, 20)
    assert rep["interval"][0] < 3 / 20 < rep["interval"][1]
    # 60 jev answers at 0.00002 and 20 repeat calls at 0.00001
    assert out["spend_usd"] == pytest.approx(60 * 0.00002 + 20 * 0.00001)
    assert e16(results(jev_1_13=jev, jev_hybrid=jev_rows()), items())["repeatability"] is None


def test_the_table_row_for_e16_reads_like_the_others() -> None:
    out = e16(results(jev_1_13=jev_rows(a6a9_wrong=6), jev_hybrid=jev_rows(cost=0.0004)), items())
    (row,) = table([out])
    assert (row["experiment"], row["winner"]) == ("E16", "jev-hybrid")
    assert "accuracy 60/60" in row["evidence"] and "USD" in row["evidence"]
    assert "jev-1.13" in row["why_others_lost"]
