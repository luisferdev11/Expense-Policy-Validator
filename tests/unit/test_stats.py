"""Statistics used by the experiments; every expected value is worked out by hand (T002)."""

import pytest

from eval.stats import brier, coverage_accuracy, ece, mcnemar_exact, paired_bootstrap, wilson


def test_wilson_textbook_value() -> None:
    lo, hi = wilson(1, 9)
    assert lo == pytest.approx(0.0199, abs=1e-3)
    assert hi == pytest.approx(0.4350, abs=1e-3)


def test_mcnemar_exact_two_sided() -> None:
    # b=1, c=6: 7 discordant pairs; P(X<=1 | n=7, p=.5) = 8/128 = 0.0625; two-sided = 0.125.
    assert mcnemar_exact(1, 6) == pytest.approx(0.125)
    assert mcnemar_exact(0, 0) == 1.0
    assert mcnemar_exact(3, 3) == 1.0


def test_paired_bootstrap_is_deterministic_and_covers_the_observed_difference() -> None:
    a = [1, 1, 1, 1, 0, 1, 1, 1, 1, 1] * 5  # 90 % correct
    b = [1, 0, 1, 1, 0, 1, 1, 0, 1, 1] * 5  # 70 % correct
    first = paired_bootstrap(a, b, seed=7, resamples=2000)
    assert first == paired_bootstrap(a, b, seed=7, resamples=2000)
    diff, lo, hi = first
    assert diff == pytest.approx(0.2)
    assert lo <= 0.2 <= hi


def test_brier_score() -> None:
    assert brier([1.0, 0.0], [True, False]) == 0.0
    # (0.8-1)^2 + (0.6-0)^2 = 0.04 + 0.36 = 0.40, over 2 items = 0.20
    assert brier([0.8, 0.6], [True, False]) == pytest.approx(0.20)


def test_ece_ten_bins_hand_example() -> None:
    # Bin [0.9, 1.0]: two items at 0.95, one correct -> |0.95 - 0.5| = 0.45, weight 2/4.
    # Bin [0.5, 0.6): two items at 0.55, both correct -> |0.55 - 1.0| = 0.45, weight 2/4.
    value = ece([0.95, 0.95, 0.55, 0.55], [True, False, True, True])
    assert value == pytest.approx(0.45)


def test_coverage_accuracy_points_are_monotone() -> None:
    points = coverage_accuracy([0.9, 0.8, 0.7, 0.6], [True, True, False, True])
    coverages = [p["coverage"] for p in points]
    assert coverages == sorted(coverages)
    full = points[-1]
    assert full["coverage"] == 1.0 and full["accuracy"] == pytest.approx(0.75)
