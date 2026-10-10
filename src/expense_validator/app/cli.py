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

from expense_validator.adapters.classification_cache import ClassificationCache
from expense_validator.adapters.config_files import load_pipeline_config, load_settings
from expense_validator.adapters.keyword_classifier import KeywordClassifier
from expense_validator.adapters.openrouter.classifier import OpenRouterClassifier
from expense_validator.adapters.openrouter.models import PINS
from expense_validator.adapters.openrouter.prompt_sync import sync_prompt
from expense_validator.adapters.receipts_file import load_receipts
from expense_validator.adapters.results_files import write_results
from expense_validator.adapters.sqlite_store import SqliteStore
from expense_validator.adapters.tracing import make_tracer
from expense_validator.app.pipeline import run_pipeline
from expense_validator.app.worker import Worker
from expense_validator.paths import (
    BASELINES_DIR,
    CLASSIFICATIONS_FILE,
    DEV_OUTPUTS_DIR,
    EVAL_DIR,
    REPO_ROOT,
    RESULTS_FILE,
)
from expense_validator.ports.classifier import ItemClassifier

# Latest run per results file, so a baseline run never hides the pipeline run (gitignored).
RUNS_FILE = REPO_ROOT / ".cache" / "runs.json"


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
    config = load_pipeline_config()
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
        clf = OpenRouterClassifier(
            cache,
            tracer,
            offline=offline,
            prompt_link=prompt_link,
            pin=PINS[config.classifier_model],
            null_subtype_as_none=config.null_subtype_as_none,
        )
    elif classifier == "keyword":
        clf = KeywordClassifier()
    else:
        raise SystemExit(f"unknown classifier: {classifier}")
    results = run_pipeline(receipts, clf, tracer, settings, run_label, config)
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
    runs = json.loads(RUNS_FILE.read_text(encoding="utf-8")) if RUNS_FILE.exists() else {}
    runs[str(path)] = asdict(summary)
    RUNS_FILE.parent.mkdir(parents=True, exist_ok=True)
    RUNS_FILE.write_text(json.dumps(runs, indent=2, sort_keys=True), encoding="utf-8")
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
    from eval.scores import post_scores

    load_env()
    metrics = run_eval(results_path=RESULTS_FILE, out_dir=EVAL_DIR)
    posted = 0
    runs = json.loads(RUNS_FILE.read_text(encoding="utf-8")) if RUNS_FILE.exists() else {}
    last = runs.get(str(RESULTS_FILE))
    # Scores go only on a run that was traced; an untraced run's trace IDs do not exist.
    if last and last.get("tracer_enabled"):
        posted = post_scores(metrics["rows"], run_label=last["run_label"])
    print(f"epv eval: wrote {EVAL_DIR}; {posted} Langfuse scores posted", file=sys.stderr)
    return 0


@dataclass(frozen=True)
class WorkerOptions:
    offline: bool = False
    no_trace: bool = False
    cache: Path | None = None


def _build_worker(store: SqliteStore, options: WorkerOptions) -> Worker:
    from expense_validator.app.composition import build_worker
    from expense_validator.paths import APP_CLASSIFICATION_CACHE

    load_env()
    return build_worker(
        store,
        offline=options.offline,
        no_trace=options.no_trace,
        cache_path=options.cache or APP_CLASSIFICATION_CACHE,
    )


def serve_command(
    host: str,
    port: int,
    db: str | None,
    worker: WorkerOptions | None = None,
    no_trace: bool = False,
) -> int:
    """Run the API; with `worker` options, a worker thread runs beside it (for demos)."""
    import threading

    import uvicorn

    from expense_validator.app.api import create_app
    from expense_validator.app.composition import (
        build_review,
        build_service,
        db_path,
        open_store,
    )

    load_env()
    path = db_path(db)
    store = open_store(path)
    service = build_service(store)
    app = create_app(service, build_review(store, service, no_trace=no_trace))
    stop = threading.Event()
    if worker is not None:
        in_process = _build_worker(store, worker)
        threading.Thread(target=in_process.run_forever, args=(1.0, stop), daemon=True).start()
    where = "in process" if worker is not None else "separate"
    print(f"epv serve: http://{host}:{port} (database {path}, worker {where})", file=sys.stderr)
    try:
        uvicorn.run(app, host=host, port=port, log_level="info")
    finally:
        stop.set()
    return 0


def worker_command(
    db: str | None,
    once: bool = False,
    poll_seconds: float = 1.0,
    options: WorkerOptions | None = None,
) -> int:
    from expense_validator.app.composition import db_path, open_store

    path = db_path(db)
    worker = _build_worker(open_store(path), options or WorkerOptions())
    if once:
        processed = worker.run_once()
        print(f"epv worker: processed {processed} work items (database {path})", file=sys.stderr)
        return 0
    print(f"epv worker: polling every {poll_seconds}s (database {path})", file=sys.stderr)
    try:
        worker.run_forever(poll_seconds)
    except KeyboardInterrupt:
        worker.tracer.flush()
    return 0


def _options(args: argparse.Namespace) -> WorkerOptions:
    return WorkerOptions(args.offline, args.no_trace, Path(args.cache) if args.cache else None)


def _cmd_serve(args: argparse.Namespace) -> int:
    return serve_command(
        args.host,
        args.port,
        args.db,
        _options(args) if args.with_worker else None,
        no_trace=args.no_trace,
    )


def _cmd_worker(args: argparse.Namespace) -> int:
    return worker_command(args.db, args.once, args.poll_seconds, _options(args))


def _add_worker_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--offline", action="store_true", help="never call a model")
    parser.add_argument("--no-trace", action="store_true", help="force the no-op tracer")
    parser.add_argument(
        "--cache", help="answer cache file (default: .cache/app_classifications.jsonl)"
    )


def _cmd_view(args: argparse.Namespace) -> int:
    app = REPO_ROOT / "viewer" / "app.py"
    return subprocess.call([sys.executable, "-m", "streamlit", "run", str(app)])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="epv", description="Expense Policy Validator")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="validate every receipt and write the results")
    run.add_argument("--classifier", choices=["openrouter", "keyword"], default="openrouter")
    run.add_argument("--offline", action="store_true", help="never call a model")
    run.add_argument("--no-trace", action="store_true", help="force the no-op tracer")
    run.add_argument("--only", nargs="+", metavar="RECEIPT_ID", help="development only")
    run.set_defaults(func=_cmd_run)
    sub.add_parser("eval", help="score committed results").set_defaults(func=_cmd_eval)
    sub.add_parser("view", help="launch the Streamlit viewer").set_defaults(func=_cmd_view)
    serve = sub.add_parser("serve", help="run the HTTP API")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--db", help="SQLite file (default: $EPV_DB or var/epv.sqlite3)")
    serve.add_argument("--with-worker", action="store_true", help="also run a worker thread")
    _add_worker_options(serve)
    serve.set_defaults(func=_cmd_serve)
    worker = sub.add_parser("worker", help="run the worker that processes submitted receipts")
    worker.add_argument("--db", help="SQLite file (default: $EPV_DB or var/epv.sqlite3)")
    worker.add_argument("--once", action="store_true", help="drain the queue and exit")
    worker.add_argument("--poll-seconds", type=float, default=1.0)
    _add_worker_options(worker)
    worker.set_defaults(func=_cmd_worker)
    args = parser.parse_args(argv)
    code: int = args.func(args)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
