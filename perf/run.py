"""Runs one load profile end to end: a fresh database, the API and workers, Locust, the report.

    uv run python -m perf.run --profile smoke
    uv run python -m perf.run --profile nominal --workers 5

It is what `specs/006-api-hardening/quickstart.md` section 6 does by hand, in one command: it
starts `epv serve --with-worker` on a throwaway SQLite file, adds `--workers - 1` separate
`epv worker` processes on the same file, runs Locust headless with the profile, then builds the
report (with `--drain`) into `docs/perf/<date>-<profile>.md` and the raw files into
`docs/perf/raw/<date>-<profile>/`. Everything it starts is stopped when it ends. The `live`
profile bills OpenRouter (capped at USD 0.25 per process) and needs the key in `.env`; run it
only on purpose.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

from perf import report
from perf.profiles import PROFILES, Profile

ROOT = Path(__file__).resolve().parents[1]
LIVE_CAP_USD = "0.25"


def _classifier_flags(profile: Profile) -> list[str]:
    flags = ["--no-trace", "--classifier", profile.classifier]
    if profile.latency_ms:
        flags += ["--simulated-latency-ms", str(profile.latency_ms)]
    if profile.classifier == "openrouter":
        flags += ["--cap-usd", LIVE_CAP_USD]
    else:
        flags += ["--offline"]
    return flags


def _epv(*args: str) -> list[str]:
    return [sys.executable, "-m", "expense_validator.app.cli", *args]


def _wait_for_health(url: str, seconds: int = 60) -> None:
    deadline = time.time() + seconds
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"{url}/health", timeout=2):
                return
        except (urllib.error.URLError, OSError):
            time.sleep(0.5)
    raise SystemExit(f"the API did not answer at {url} within {seconds} s")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="perf.run", description=(__doc__ or "").split("\n")[0])
    parser.add_argument("--profile", required=True, choices=sorted(PROFILES))
    parser.add_argument("--workers", type=int, help="worker processes (default: the profile's)")
    parser.add_argument("--port", type=int, default=8781)
    parser.add_argument("--drain-timeout", type=int, default=600)
    parser.add_argument("--date", default=datetime.now(UTC).strftime("%Y-%m-%d"))
    args = parser.parse_args(argv)
    profile = PROFILES[args.profile]
    workers = args.workers or profile.workers
    host = f"http://127.0.0.1:{args.port}"
    raw = ROOT / "docs" / "perf" / "raw" / f"{args.date}-{profile.name}"
    out = ROOT / "docs" / "perf" / f"{args.date}-{profile.name}.md"
    raw.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="epv-perf-") as directory:
        db = str(Path(directory) / "perf.sqlite3")
        flags = _classifier_flags(profile)
        csv_prefix = f"docs/perf/raw/{args.date}-{profile.name}/locust"
        locust = [
            str(Path(sys.executable).parent / "locust"),
            "-f", "perf/locustfile.py", "--headless", "--host", host,
            "--profile", profile.name, "--csv", str(ROOT / csv_prefix), "--only-summary",
        ]  # fmt: skip
        serve = _epv("serve", "--port", str(args.port), "--db", db, "--with-worker", *flags)
        # What the report shows: the commands without this machine's paths.
        shown = (
            f"uv run epv serve --port {args.port} --db <temporary file> --with-worker "
            f"{' '.join(flags)}; {workers - 1} more `epv worker` processes on the same file; "
            f"uv run locust -f perf/locustfile.py --headless --host {host} "
            f"--profile {profile.name} --csv {csv_prefix}"
        )
        (raw / "command.txt").write_text(shown + "\n", encoding="utf-8")
        processes = [subprocess.Popen(serve, cwd=ROOT)]
        try:
            _wait_for_health(host)
            for _ in range(workers - 1):
                processes.append(subprocess.Popen(_epv("worker", "--db", db, *flags), cwd=ROOT))
            subprocess.run(locust, cwd=ROOT, check=True)
            report.main(
                [
                    "--profile", profile.name, "--raw", str(raw), "--out", str(out),
                    "--drain", "--host", host, "--drain-timeout", str(args.drain_timeout),
                ]
            )  # fmt: skip
        finally:
            for process in processes:
                process.terminate()
            for process in processes:
                try:
                    process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    process.kill()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
