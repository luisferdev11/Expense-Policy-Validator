"""Base rate: what the measured rates mean at a realistic prevalence (T083, FR-033)."""

import pytest

from eval.base_rate import base_rate_table


def test_hand_arithmetic_at_3_percent() -> None:
    # 1 false positive of 9 should-pass, 1 missed of 16 should-flag:
    # FPR = 1/9, detection = 15/16. Per 10,000 at 3 %: 300 violations, 9,700 clean.
    # True flags = 300 * 15/16 = 281.25; false flags = 9,700 / 9 = 1,077.78.
    # Share of flags that are false = 1,077.78 / 1,359.03 = 0.793.
    table = base_rate_table(fp=1, n_pass=9, missed=1, n_flag=16, prevalences=(0.03,))
    (row,) = table["rows"]
    assert row["true_flags"] == pytest.approx(281.25)
    assert row["false_flags"] == pytest.approx(1077.78, abs=0.01)
    assert row["false_share"] == pytest.approx(0.793, abs=0.001)
    assert table["n_pass"] == 9 and table["n_flag"] == 16


def test_default_prevalences() -> None:
    table = base_rate_table(fp=0, n_pass=9, missed=0, n_flag=16)
    assert [r["prevalence"] for r in table["rows"]] == [0.01, 0.03, 0.05]
    assert all(r["false_flags"] == 0 for r in table["rows"])
