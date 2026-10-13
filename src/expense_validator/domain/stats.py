"""Statistics that the package itself needs: the Wilson interval (spec 007, research R6).

Pure and deterministic. It lives here, not in `eval/`, because the shadow report reads the store and
computes intervals, and the package may not import `eval/`. `eval/stats.py` re-exports it, so every
existing caller keeps one implementation.
"""

from __future__ import annotations

import math

Z95 = 1.959963984540054


def wilson(k: int, n: int) -> tuple[float, float]:
    """Wilson score 95 % interval for k successes out of n."""
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    denom = 1 + Z95**2 / n
    centre = (p + Z95**2 / (2 * n)) / denom
    half = Z95 * math.sqrt(p * (1 - p) / n + Z95**2 / (4 * n * n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))
