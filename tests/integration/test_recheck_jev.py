"""SC-003: the corrected rule keeps E14's winner and fails the 2026-10-11 jev rows on the guard."""

from __future__ import annotations

import json

import pytest

from eval.experiments import recheck_jev_2026_10_11 as recheck
from expense_validator.paths import EVAL_DIR


def test_the_corrected_rule_fails_jev_1_13_on_the_a6a9_guard(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert recheck.main() == 0
    out = capsys.readouterr().out
    assert "jev-1.13: fails_a6a9_guard" in out
    assert "winner: gpt-oss-120b" in out


def test_the_committed_e14_outcome_is_the_one_the_corrected_rule_gives() -> None:
    from eval.experiments.decide import _load, e14
    from eval.experiments.devset import load_frozen
    from eval.experiments.run_dev import RESULTS

    committed = json.loads((EVAL_DIR / "experiments.json").read_text(encoding="utf-8"))
    (expected,) = [e for e in committed["experiments"] if e["id"] == "E14"]
    rows = {p.stem: _load(p) for p in sorted((RESULTS / "E14").glob("*.jsonl"))}
    assert e14(rows, load_frozen()) == expected
