"""Evaluation metrics on hand-built rows; every expected number is worked out by hand (T077)."""

from typing import Any

import pytest

from eval.metrics import (
    false_positives,
    macro_f1,
    missed_violations,
    restricted_f1,
    wilson,
)


def line(pred: str | None, ans: str, pred_r: bool | None, ans_r: bool) -> dict[str, Any]:
    return {
        "line_id": "x",
        "predicted_category": pred,
        "answer_category": ans,
        "predicted_restricted": pred_r,
        "answer_restricted": ans_r,
    }


def row(lines: list[dict[str, Any]], pred: str = "pass", ans: str = "pass", scored: bool = True):  # type: ignore[no-untyped-def]
    return {
        "receipt_id": "SYN",
        "scored": scored,
        "lines": lines,
        "predicted_disposition": pred,
        "answer_disposition": ans,
    }


def test_macro_f1_counts_a_never_predicted_category_as_zero() -> None:
    rows = [
        row(
            [
                line("alcohol", "alcohol", True, True),  # alcohol TP
                line("food_beverage", "alcohol", False, True),  # alcohol FN, food FP
                line("food_beverage", "food_beverage", False, False),  # food TP
                line("other", "gift", False, True),  # gift never predicted; other is FP only
            ]
        )
    ]
    # alcohol: P=1/1, R=1/2 -> F1=2/3. food: P=1/2, R=1/1 -> F1=2/3. gift: P=0 -> F1=0.
    # Macro over answer categories {alcohol, food_beverage, gift} = (2/3 + 2/3 + 0)/3 = 4/9.
    m = macro_f1(rows)
    assert m["value"] == pytest.approx(4 / 9)
    assert m["n"] == 4
    assert m["categories"] == 3


def test_macro_f1_skips_unscored_receipts() -> None:
    rows = [row([line("alcohol", "alcohol", True, True)], scored=False)]
    assert macro_f1(rows)["n"] == 0


def test_restricted_f1_positive_class_is_true_and_none_counts_as_negative() -> None:
    rows = [
        row(
            [
                line("alcohol", "alcohol", True, True),  # TP
                line(None, "gift", None, True),  # FN (unclassified)
                line("gift", "food_beverage", True, False),  # FP
                line("office_supplies", "office_supplies", False, False),  # TN
            ]
        )
    ]
    # P = 1/2, R = 1/2 -> F1 = 1/2
    m = restricted_f1(rows)
    assert m["value"] == pytest.approx(0.5)
    assert m["n"] == 4


def test_false_positives_out_of_should_pass() -> None:
    rows = [
        row([], pred="review", ans="pass"),
        row([], pred="pass", ans="pass"),
        row([], pred="flag", ans="pass"),
        row([], pred="flag", ans="flag"),
    ]
    m = false_positives(rows)
    assert (m["value"], m["n"]) == (2, 3)


def test_missed_violations_out_of_should_flag() -> None:
    rows = [
        row([], pred="review", ans="flag"),
        row([], pred="pass", ans="flag"),
        row([], pred="flag", ans="flag"),
        row([], pred="flag", ans="review"),
    ]
    m = missed_violations(rows)
    assert (m["value"], m["n"]) == (2, 3)


def test_wilson_interval_matches_the_textbook_value() -> None:
    # 1 of 9: Wilson 95 % interval is about [0.0199, 0.4350].
    lo, hi = wilson(1, 9)
    assert lo == pytest.approx(0.0199, abs=1e-3)
    assert hi == pytest.approx(0.4350, abs=1e-3)
    assert wilson(0, 0) == (0.0, 1.0)
