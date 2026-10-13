"""Re-judge the demonstrative jev-1.13 run of 2026-10-11 under the corrected rule (spec 007, T005).

    uv run python -I eval/experiments/recheck_jev_2026_10_11.py

The 2026-10-11 run (`frontend/data/jev-1.13-dev.jsonl`, N = 130) was labelled `superior` by the
rule as it was coded, although jev returns no subtype or recipient and gets 23 of 29 A6/A9 items
wrong. This reads the committed E14 rows and those jev rows, applies `decide.e14` (guards before
superiority), prints each variant's status and exits non-zero unless jev-1.13 is
`fails_a6a9_guard` and the winner is the reference. It writes nothing. It lives under `eval/`
because it reads the frozen dev set's labels (principle I).
"""

from __future__ import annotations

import sys

from eval.experiments.decide import REFERENCE, _load, e14
from eval.experiments.devset import load_frozen
from eval.experiments.run_dev import RESULTS
from expense_validator.paths import REPO_ROOT

JEV_ROWS = REPO_ROOT / "frontend" / "data" / "jev-1.13-dev.jsonl"
VARIANT = "jev-1.13"


def main() -> int:
    items = load_frozen()
    results = {p.stem: _load(p) for p in sorted((RESULTS / "E14").glob("*.jsonl"))}
    results[VARIANT] = _load(JEV_ROWS)
    outcome = e14(results, items)
    for v in outcome["variants"]:
        a6a9 = f"{v['a6a9_wrong']}/{v['a6a9_n']}"
        print(f"{v['variant']}: {v['status']} (accuracy {v['accuracy']['k']}/{v['accuracy']['n']}, "
              f"A6/A9 wrong {a6a9})")  # fmt: skip
    print(f"winner: {outcome['winner']}")
    by = {v["variant"]: v for v in outcome["variants"]}
    ok = by[VARIANT]["status"] == "fails_a6a9_guard" and outcome["winner"] == REFERENCE
    if not ok:
        print("unexpected: jev-1.13 should fail the A6/A9 guard and the reference should win")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
