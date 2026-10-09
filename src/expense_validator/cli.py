"""`epv` command line: run, eval, view (contracts/cli.md, FR-035).

`epv eval` imports the evaluation package lazily inside `_cmd_eval`; that is the only import of
`eval` allowed outside it (analysis I2). Keys come from `.env` and are never printed.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from expense_validator.classification.cache import ClassificationCache
from expense_validator.classification.openrouter import OpenRouterClassifier
from expense_validator.classification.port import ItemClassifier
from expense_validator.classification.prompt_sync import sync_prompt
from expense_validator.engine.settings import load_settings
from expense_validator.loader import load_receipts
from expense_validator.paths import (
    BASELINES_DIR,
    CLASSIFICATIONS_FILE,
    DEV_OUTPUTS_DIR,
    EVAL_DIR,
    REPO_ROOT,
    RESULTS_FILE,
)
from expense_validator.pipeline import run_pipeline, write_results
from expense_validator.tracing import make_tracer

LAST_RUN_FILE = REPO_ROOT / ".cache" / "last_run.json"


@dataclass(frozen=True)
class RunSummary:
    receipts: int
    classifier: str
    calls_made: int
    cache_hits: int
    billed_usd: float
    tracer_enabled: bool
    run_label: str
    results_path: str


def load_env() -> None:
    from dotenv import load_dotenv

    load_dotenv(REPO_ROOT / ".env")


def default_results_path(classifier: str, only: list[str] | None) -> Path:
    if only:
        return DEV_OUTPUTS_DIR / "results.jsonl"
    if classifier == "keyword":
        return BASELINES_DIR / "keyword_classifier" / "results.jsonl"
    return RESULTS_FILE


def run_command(
    classifier: str = "openrouter",
    offline: bool = False,
    no_trace: bool = False,
    only: list[str] | None = None,
    results_path: Path | None = None,
    cache_path: Path = CLASSIFICATIONS_FILE,
) -> RunSummary:
    load_env()
    settings = load_settings()
    receipts = load_receipts()
    if only:
        wanted = set(only)
        receipts = [r for r in receipts if r.receipt_id in wanted]
    tracer = make_tracer(disabled=no_trace)
    run_label = f"run-{datetime.now(UTC):%Y%m%dT%H%M%SZ}"
    cache = ClassificationCache(cache_path)
    clf: ItemClassifier
    if classifier == "openrouter":
        prompt_link = None if offline else sync_prompt(tracer)
        clf = OpenRouterClassifier(cache, tracer, offline=offline, prompt_link=prompt_link)
    else:
        raise SystemExit(f"unknown classifier: {classifier}")
    results = run_pipeline(receipts, clf, tracer, settings, run_label)
    path = results_path or default_results_path(classifier, only)
    write_results(path, results)
    if cache.dirty:
        cache.save()
    tracer.flush(timeout_s=10.0)
    summary = RunSummary(
        receipts=len(results),
        classifier=clf.name,
        calls_made=getattr(clf, "calls_made", 0),
        cache_hits=getattr(clf, "cache_hits", 0),
        billed_usd=round(getattr(clf, "run_spend_usd", 0.0), 6),
        tracer_enabled=tracer.enabled,
        run_label=run_label,
        results_path=str(path),
    )
    LAST_RUN_FILE.parent.mkdir(parents=True, exist_ok=True)
    LAST_RUN_FILE.write_text(json.dumps(asdict(summary), indent=2), encoding="utf-8")
    return summary


def _cmd_run(args: argparse.Namespace) -> int:
    summary = run_command(
        classifier=args.classifier, offline=args.offline, no_trace=args.no_trace, only=args.only
    )
    print(
        f"epv run: {summary.receipts} receipts, {summary.calls_made} model calls, "
        f"{summary.cache_hits} cache hits, billed USD {summary.billed_usd:.6f}, "
        f"tracing {'on' if summary.tracer_enabled else 'off'} -> {summary.results_path}",
        file=sys.stderr,
    )
    return 0


def _cmd_eval(args: argparse.Namespace) -> int:
    from eval.report import run_eval

    run_eval(results_path=RESULTS_FILE, out_dir=EVAL_DIR)
    print(f"epv eval: wrote {EVAL_DIR}", file=sys.stderr)
    return 0


def _cmd_view(args: argparse.Namespace) -> int:
    app = REPO_ROOT / "viewer" / "app.py"
    return subprocess.call([sys.executable, "-m", "streamlit", "run", str(app)])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="epv", description="Expense Policy Validator")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="validate every receipt and write the results")
    run.add_argument("--classifier", choices=["openrouter"], default="openrouter")
    run.add_argument("--offline", action="store_true", help="never call a model")
    run.add_argument("--no-trace", action="store_true", help="force the no-op tracer")
    run.add_argument("--only", nargs="+", metavar="RECEIPT_ID", help="development only")
    run.set_defaults(func=_cmd_run)
    sub.add_parser("eval", help="score committed results").set_defaults(func=_cmd_eval)
    sub.add_parser("view", help="launch the Streamlit viewer").set_defaults(func=_cmd_view)
    args = parser.parse_args(argv)
    code: int = args.func(args)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
