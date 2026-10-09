"""epv eval is byte-reproducible, needs no key and posts no scores without Langfuse
(T085, T086, FR-029, SC-004)."""

import warnings
from pathlib import Path

from eval.report import run_eval
from eval.scores import post_scores
from expense_validator.app.cli import run_command


def test_eval_twice_is_byte_identical(tmp_path: Path) -> None:
    results = tmp_path / "results.jsonl"
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        run_command(offline=True, no_trace=True, results_path=results)
    out1, out2 = tmp_path / "e1", tmp_path / "e2"
    run_eval(results_path=results, out_dir=out1, baselines={})
    run_eval(results_path=results, out_dir=out2, baselines={})
    for name in ("comparison.jsonl", "metrics.json", "report.md"):
        assert (out1 / name).read_bytes() == (out2 / name).read_bytes(), name


def test_scores_are_a_no_op_without_keys(tmp_path: Path) -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        posted = post_scores(rows=[], run_label="none", env={})
    assert posted == 0
