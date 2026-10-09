"""What the measured rates mean at a realistic prevalence (FR-033, brief Part 3).

This dataset is more than half violations; a real expense stream has a few percent. Using the
measured false-positive rate (should-pass receipts flagged or sent to review) and detection rate
(should-flag receipts flagged), compute per 10,000 receipts how many flags would be true and
how many false.
"""

from __future__ import annotations

from typing import Any

RECEIPTS = 10_000
PREVALENCES = (0.01, 0.03, 0.05)


def base_rate_table(
    fp: int, n_pass: int, missed: int, n_flag: int, prevalences: tuple[float, ...] = PREVALENCES
) -> dict[str, Any]:
    fpr = fp / n_pass if n_pass else 0.0
    detection = (n_flag - missed) / n_flag if n_flag else 0.0
    rows = []
    for p in prevalences:
        violations = RECEIPTS * p
        true_flags = detection * violations
        false_flags = fpr * (RECEIPTS - violations)
        total = true_flags + false_flags
        rows.append(
            {
                "prevalence": p,
                "violations": violations,
                "true_flags": true_flags,
                "false_flags": false_flags,
                "false_share": (false_flags / total) if total else 0.0,
            }
        )
    return {
        "receipts": RECEIPTS,
        "false_positive_rate": fpr,
        "detection_rate": detection,
        "n_pass": n_pass,
        "n_flag": n_flag,
        "rows": rows,
    }
