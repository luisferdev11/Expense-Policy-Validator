"""Locust scenarios for the API (spec 006, US5).

    uv run locust -f perf/locustfile.py --headless --host http://127.0.0.1:8000 \
        --profile smoke --csv docs/perf/raw/<date>-smoke/locust

`--profile` (smoke, nominal, peak or live) sets the user count, spawn rate and run time from
`perf/profiles.py` unless `-u`, `-r` or `-t` are given, and the pause between a user's tasks so
that the users together submit the profile's receipts a second. The option is Locust's own (a
free-text label that groups runs), which this file reads and checks; it adds no argument.
A background greenlet samples `GET /health` `open_work` every 0.5 s into `backlog.csv`; when the
test stops, `stop.json` records the moment, so `perf.report --drain` can measure how long the
queue takes to empty. The tasks are in `perf/tasks.py`, which does not import Locust, so tests
can run them without it.
"""

from __future__ import annotations

import csv
import itertools
import json
import os
import random
import time
from pathlib import Path
from typing import Any, cast

import gevent
from locust import HttpUser, events, task

from perf import tasks
from perf.profiles import PROFILES, Profile, user_wait_seconds, weights

SAMPLE_EVERY_S = 0.5

_run: dict[str, Any] = {}


def _raw_dir(options: Any) -> Path:
    prefix = getattr(options, "csv_prefix", None)
    return Path(prefix).parent if prefix else Path(".")


def apply_profile(environment: Any, **_: Any) -> None:
    options = environment.parsed_options
    name = options.profile or "smoke"
    if name not in PROFILES:
        raise SystemExit(f"unknown profile {name!r}; choose one of {', '.join(sorted(PROFILES))}")
    profile = PROFILES[name]
    if options.num_users is None:
        options.num_users = profile.users
    if options.spawn_rate is None:
        options.spawn_rate = profile.spawn_rate
    if options.run_time is None:
        options.run_time = profile.run_time_s
    _run.update(
        profile=profile,
        id=time.strftime("%H%M%S"),
        numbers=itertools.count(1),
        started_at=None,
        backlog=[],
    )


def _sample_backlog(host: str, samples: list[tuple[float, int]], t0: float) -> None:
    import requests  # here, not at the top: it must not load `ssl` before Locust patches it

    while True:
        try:
            open_work = requests.get(f"{host}/health", timeout=5).json()["open_work"]
            samples.append((round(time.time() - t0, 1), int(open_work)))
        except (requests.RequestException, KeyError, ValueError):
            pass  # a missed sample is a gap, not a failure of the test
        gevent.sleep(SAMPLE_EVERY_S)


def start_sampling(environment: Any, **_: Any) -> None:
    _raw_dir(environment.parsed_options).mkdir(parents=True, exist_ok=True)
    _run["started_at"] = time.time()
    _run["sampler"] = gevent.spawn(
        _sample_backlog, environment.host, _run["backlog"], _run["started_at"]
    )


def write_stop_files(environment: Any, **_: Any) -> None:
    sampler = _run.get("sampler")
    if sampler is not None:
        sampler.kill()
    raw = _raw_dir(environment.parsed_options)
    raw.mkdir(parents=True, exist_ok=True)
    with (raw / "backlog.csv").open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["elapsed_s", "open_work"])
        writer.writerows(_run.get("backlog", []))
    profile: Profile = _run["profile"]
    (raw / "stop.json").write_text(
        json.dumps(
            {
                "profile": profile.name,
                "run_id": _run["id"],
                "users": environment.parsed_options.num_users,
                "started_at": _run["started_at"],
                "stopped_at": time.time(),
            }
        )
        + "\n",
        encoding="utf-8",
    )


events.init.add_listener(apply_profile)  # type: ignore[no-untyped-call]
events.test_start.add_listener(start_sampling)  # type: ignore[no-untyped-call]
events.test_stop.add_listener(write_stop_files)  # type: ignore[no-untyped-call]


class Reviewer(HttpUser):
    """One simulated user mixing the tasks of `perf/tasks.py` by the profile's weights."""

    abstract = False

    def on_start(self) -> None:
        self.profile: Profile = _run["profile"]
        self.ctx = tasks.UserContext(
            run_id=_run["id"], rng=random.Random(os.getpid() + id(self)), numbers=_run["numbers"]
        )
        w = weights(self.profile)
        self._names = list(w)
        self._weights = list(w.values())
        self._actions = {
            "submit": tasks.submit_receipt,
            "submit_key": tasks.submit_with_key,
            "batch": tasks.submit_batch,
            "list": tasks.list_by_updated,
            "detail": tasks.read_detail,
            "approve": tasks.approve_flagged,
        }

    def wait_time(self) -> float:
        return user_wait_seconds(self.profile)

    @task
    def act(self) -> None:
        name = self.ctx.rng.choices(self._names, self._weights)[0]
        self._actions[name](cast(Any, self.client), self.ctx)
