"""Turns the raw files of a load run into a Markdown report with every figure's N (research R15).

    uv run python -m perf.report --profile smoke --raw docs/perf/raw/<date>-smoke \
        --out docs/perf/<date>-smoke.md --drain --host http://127.0.0.1:8000

Reads Locust's CSV files (`locust_stats.csv`, `locust_stats_history.csv`, `locust_failures.csv`)
and the files the locustfile and this module write beside them: `stop.json` (when the load
stopped), `backlog.csv` (`open_work` from `GET /health`, every 0.5 s) and `drain.json` (written by
`--drain`, which polls `GET /health` until `open_work` is 0). The queue is judged only through
`/health`. Without `--drain` the report is rebuilt from committed raw data, with no load run.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import platform
import sqlite3
import subprocess
import sys
import time
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from perf.profiles import DRAIN_OK_SECONDS, PROFILES, READ_P95_MS, SUBMIT_P95_MS, kind

RESTING = ("auto_approved", "in_review", "compliance")


@dataclass(frozen=True)
class RunInfo:
    commit: str
    date: str
    python: str
    sqlite: str
    cpu: str
    cores: int
    command: str


def machine_info(command: str = "") -> RunInfo:
    cpu = platform.processor() or platform.machine()
    cpuinfo = Path("/proc/cpuinfo")
    if cpuinfo.exists():
        for line in cpuinfo.read_text(encoding="utf-8").splitlines():
            if line.startswith("model name"):
                cpu = line.split(":", 1)[1].strip()
                break
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=True
        ).stdout.strip()
        changed = subprocess.run(
            ["git", "status", "--porcelain", "--", ".", ":!docs/perf"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        if changed:
            commit += " (with uncommitted changes)"
    except (OSError, subprocess.CalledProcessError):
        commit = "unknown"
    return RunInfo(
        commit=commit,
        date=datetime.now(UTC).strftime("%Y-%m-%d"),
        python=platform.python_version(),
        sqlite=sqlite3.sqlite_version,
        cpu=cpu,
        cores=os.cpu_count() or 1,
        command=command,
    )


def _rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def _int(text: str) -> int:
    return int(float(text)) if text not in ("", "N/A") else 0


def _endpoint_table(stats: list[dict[str, str]]) -> tuple[list[str], list[tuple[str, str, int]]]:
    """Table lines, and (method, name, p95 ms) of every endpoint for the thresholds."""
    lines = [
        "| endpoint | N | failures | p50 ms | p95 ms | p99 ms | requests a second |",
        "|---|---|---|---|---|---|---|",
    ]
    p95s: list[tuple[str, str, int]] = []
    for row in stats:
        aggregated = row["Name"] == "Aggregated"
        label = "all requests" if aggregated else f"{row['Type']} {row['Name']}"
        p95 = _int(row["95%"])
        lines.append(
            f"| {label} | {_int(row['Request Count'])} | {_int(row['Failure Count'])} "
            f"| {_int(row['50%'])} | {p95} | {_int(row['99%'])} "
            f"| {float(row['Requests/s']):.2f} |"
        )
        if not aggregated:
            p95s.append((row["Type"], row["Name"], p95))
    return lines, p95s


def _queue_lines(raw: Path, drain: dict[str, Any] | None) -> list[str]:
    backlog = _rows(raw / "backlog.csv")
    lines = []
    if backlog:
        peak = max(_int(r["open_work"]) for r in backlog)
        lines.append(f"- Peak backlog: {peak} items ({len(backlog)} samples, every 0.5 s).")
    else:
        lines.append("- Peak backlog: not sampled.")
    if drain is None:
        lines.append("- Drain time: not measured (run `perf.report` with `--drain`).")
        return lines
    seconds = drain["drain_seconds"]
    if seconds is None:
        lines.append(
            f"- The queue did not drain within {drain['timeout_s']} s: "
            f"{drain['remaining']} items left."
        )
    else:
        lines.append(f"- Drain time: {seconds} s after the load stopped.")
    done = drain["evaluated"]
    lines.append(
        f"- Receipts evaluated: {done['total']} ("
        + ", ".join(f"{done[state]} {state}" for state in RESTING)
        + ")."
    )
    return lines


def _threshold_lines(
    profile: str, p95s: list[tuple[str, str, int]], drain: dict[str, Any] | None
) -> list[str]:
    if profile != "nominal":
        return [
            f"Thresholds apply to the `nominal` profile; `{profile}` is reported, not judged.",
        ]
    lines = []
    for method, name, p95 in p95s:
        which = kind(method, name)
        if which == "other":
            continue
        limit = SUBMIT_P95_MS if which == "submit" else READ_P95_MS
        verdict = (
            f"p95 {p95} ms is within {limit} ms (met)"
            if p95 <= limit
            else f"p95 {p95} ms is above {limit} ms (miss)"
        )
        lines.append(f"- {method} {name}: {verdict}")
    if drain is None:
        lines.append("- the queue was not measured (no `--drain`).")
    elif drain["drain_seconds"] is None:
        lines.append("- the queue did not drain (miss)")
    elif drain["drain_seconds"] <= DRAIN_OK_SECONDS:
        lines.append(f"- the queue drained {drain['drain_seconds']} s after the load stopped (met)")
    else:
        lines.append(
            f"- the queue drained {drain['drain_seconds']} s after the load stopped, "
            f"over {DRAIN_OK_SECONDS:g} s (miss)"
        )
    return lines


def render(profile_name: str, raw: Path, info: RunInfo) -> str:
    profile = PROFILES[profile_name]
    stats = _rows(raw / "locust_stats.csv")
    history = _rows(raw / "locust_stats_history.csv")
    failures = _rows(raw / "locust_failures.csv")
    drain_file = raw / "drain.json"
    drain: dict[str, Any] | None = (
        json.loads(drain_file.read_text(encoding="utf-8")) if drain_file.exists() else None
    )
    table, p95s = _endpoint_table(stats)
    users = max((_int(r["User Count"]) for r in history), default=0)
    total = next((_int(r["Request Count"]) for r in stats if r["Name"] == "Aggregated"), 0)

    out = [
        f"# Load test: {profile.name} ({info.date})",
        "",
        f"- Commit: {info.commit}",
        f"- Machine: {info.cpu}, {info.cores} cores; Python {info.python}; SQLite {info.sqlite}",
        f"- Command: `{info.command}`",
        "",
        "## Profile",
        "",
        "| profile | users | receipts a second | duration | classifier | latency per line "
        "| workers |",
        "|---|---|---|---|---|---|---|",
        f"| {profile.name} | {profile.users} | {profile.receipts_per_s:g} | {profile.run_time_s} s "
        f"| {profile.classifier} | {profile.latency_ms} ms | {profile.workers} |",
        "",
        f"{profile.purpose.capitalize()}. Users reached: {users}.",
        "",
        f"## Requests (N = {total})",
        "",
        *table,
        "",
        "### Failures",
        "",
        *(
            [
                f"- {r['Method']} {r['Name']}: {r['Error']} ({r['Occurrences']} times)"
                for r in failures
            ]
            or ["No request failed."]
        ),
        "",
        "## Queue",
        "",
        *_queue_lines(raw, drain),
        "",
        "## Thresholds",
        "",
        *_threshold_lines(profile.name, p95s, drain),
        "",
        "## Reading",
        "",
        "`docs/aws.md` sizes 100,000 receipts a day as about 1.2 receipts a second on average and "
        "about 12 at a 10x peak, on Aurora PostgreSQL and Fargate. This run used SQLite on one "
        "machine: SQLite serialises writes (`BEGIN IMMEDIATE`), every worker process shares the "
        "same file, and the client, the API and the workers share this machine's CPU. The "
        "figures say how the application behaves here, not how the AWS design would; where "
        "they miss, the limit named above is SQLite or this machine before it is the code. "
        f"The simulated classifier answers every line the same way, so only timings matter. "
        f"The profile used {profile.workers} worker process(es); one worker handles a receipt "
        f"in about (lines x latency) seconds, so the worker count is what bounds the drain time.",
        "",
    ]
    return "\n".join(out)


def _get_json(url: str) -> Any:
    with urllib.request.urlopen(url, timeout=30) as response:
        return json.loads(response.read())


def measure_drain(host: str, raw: Path, timeout_s: int) -> dict[str, Any]:
    """Poll `GET /health` until `open_work` is 0 and write `drain.json`."""
    stop = json.loads((raw / "stop.json").read_text(encoding="utf-8"))
    deadline = time.time() + timeout_s
    remaining = _get_json(f"{host}/health")["open_work"]
    while remaining > 0 and time.time() < deadline:
        time.sleep(0.5)
        remaining = _get_json(f"{host}/health")["open_work"]
    evaluated = {
        state: _get_json(f"{host}/receipts?state={state}&limit=1")["total"] for state in RESTING
    }
    drained = remaining == 0
    result = {
        "drain_seconds": round(time.time() - stop["stopped_at"], 1) if drained else None,
        "timeout_s": timeout_s,
        "remaining": remaining,
        "evaluated": {"total": sum(evaluated.values()), **evaluated},
    }
    (raw / "drain.json").write_text(json.dumps(result) + "\n", encoding="utf-8")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="perf.report", description=(__doc__ or "").split("\n")[0])
    parser.add_argument("--profile", required=True, choices=sorted(PROFILES))
    parser.add_argument("--raw", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument(
        "--drain", action="store_true", help="poll /health until the queue is empty"
    )
    parser.add_argument("--host", default="http://127.0.0.1:8000")
    parser.add_argument("--drain-timeout", type=int, default=600, help="seconds to wait")
    args = parser.parse_args(argv)
    if args.drain:
        measure_drain(args.host, args.raw, args.drain_timeout)
    command_file = args.raw / "command.txt"
    command = command_file.read_text(encoding="utf-8").strip() if command_file.exists() else ""
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(render(args.profile, args.raw, machine_info(command)), encoding="utf-8")
    print(f"perf.report: wrote {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
