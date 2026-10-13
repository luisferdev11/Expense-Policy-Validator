"""Statistics for the evaluation and the experiments. Pure and deterministic (research R5).

Ported from the evaluation study notebook (explorations/notebooks/04_evaluation_study) and
tested against hand-computed values. No scipy: each method is a few lines.
"""

from __future__ import annotations

import math
import random
from collections.abc import Sequence
from typing import Any

# The Wilson interval moved into the package (the shadow report needs it, and the package may not
# import `eval/`); it is re-exported so every caller here keeps one implementation.
from expense_validator.domain.stats import Z95 as Z95
from expense_validator.domain.stats import wilson as wilson


def mcnemar_exact(b: int, c: int) -> float:
    """Two-sided exact McNemar p-value from the discordant counts b and c."""
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / (1 << n)
    return min(1.0, 2 * tail)


def paired_bootstrap(
    a: Sequence[int], b: Sequence[int], seed: int = 20261009, resamples: int = 10_000
) -> tuple[float, float, float]:
    """Accuracy difference mean(a) - mean(b) on paired 0/1 outcomes, with a 95 % percentile CI."""
    if len(a) != len(b) or not a:
        raise ValueError("paired samples must have the same, non-zero length")
    n = len(a)
    diff = (sum(a) - sum(b)) / n
    rng = random.Random(seed)
    stats = []
    for _ in range(resamples):
        idx = [rng.randrange(n) for _ in range(n)]
        stats.append(sum(a[i] - b[i] for i in idx) / n)
    stats.sort()
    lo = stats[int(0.025 * resamples)]
    hi = stats[min(resamples - 1, int(0.975 * resamples))]
    return (diff, lo, hi)


def brier(confidences: Sequence[float], correct: Sequence[bool]) -> float:
    """Mean squared error between confidence and correctness."""
    return sum((p - float(c)) ** 2 for p, c in zip(confidences, correct, strict=True)) / len(
        confidences
    )


def ece(confidences: Sequence[float], correct: Sequence[bool], bins: int = 10) -> float:
    """Expected calibration error over equal-width bins; confidence 1.0 falls in the top bin."""
    n = len(confidences)
    total = 0.0
    for b in range(bins):
        members = [
            (p, c)
            for p, c in zip(confidences, correct, strict=True)
            if min(int(p * bins), bins - 1) == b
        ]
        if members:
            mean_p = sum(p for p, _ in members) / len(members)
            accuracy = sum(1 for _, c in members if c) / len(members)
            total += abs(mean_p - accuracy) * len(members) / n
    return total


def coverage_accuracy(
    confidences: Sequence[float], correct: Sequence[bool]
) -> list[dict[str, Any]]:
    """Keep the k most confident items, for k = 1..n: coverage, accuracy and the threshold."""
    ranked = sorted(zip(confidences, correct, strict=True), key=lambda x: -x[0])
    points = []
    hits = 0
    for k, (p, c) in enumerate(ranked, start=1):
        hits += int(c)
        points.append({"threshold": p, "coverage": k / len(ranked), "accuracy": hits / k})
    return points
