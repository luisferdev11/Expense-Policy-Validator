"""run → eval works end to end offline, and the run is byte-identical (T044, SC-003, SC-007)."""

import shutil
import warnings
from pathlib import Path

from expense_validator.cli import run_command
from expense_validator.paths import CLASSIFICATIONS_FILE


def _cache_copy(tmp_path: Path) -> Path:
    target = tmp_path / "classifications.jsonl"
    if CLASSIFICATIONS_FILE.exists():
        shutil.copy(CLASSIFICATIONS_FILE, target)
    return target


def test_offline_run_is_byte_identical_and_needs_no_tracer(tmp_path: Path) -> None:
    cache = _cache_copy(tmp_path)
    first, second = tmp_path / "r1.jsonl", tmp_path / "r2.jsonl"
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        s1 = run_command(offline=True, no_trace=True, results_path=first, cache_path=cache)
        s2 = run_command(offline=True, no_trace=True, results_path=second, cache_path=cache)
    assert first.read_bytes() == second.read_bytes()
    assert len(first.read_text(encoding="utf-8").splitlines()) == 32
    assert s1.calls_made == s2.calls_made == 0
    assert s1.billed_usd == 0.0
    assert not s1.tracer_enabled


def test_tracer_falls_back_without_keys(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    monkeypatch.setattr("expense_validator.cli.load_env", lambda: None)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        summary = run_command(
            offline=True,
            no_trace=False,
            results_path=tmp_path / "r.jsonl",
            cache_path=_cache_copy(tmp_path),
        )
    assert not summary.tracer_enabled


def test_eval_runs_on_the_offline_results(tmp_path: Path) -> None:
    from eval.report import run_eval

    results = tmp_path / "results.jsonl"
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        run_command(
            offline=True, no_trace=True, results_path=results, cache_path=_cache_copy(tmp_path)
        )
    out = tmp_path / "eval"
    run_eval(results_path=results, out_dir=out, baselines={})
    for name in ("comparison.jsonl", "metrics.json", "report.md"):
        assert (out / name).exists()
