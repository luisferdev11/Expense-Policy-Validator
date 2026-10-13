"""The load test's tasks run once against the real app, with no Locust runner (spec 006, US5).

The task functions live in `perf/tasks.py`, which never imports Locust (Locust patches the standard
library when it is imported, and that must not happen inside the test run). `perf/locustfile.py`
wires them into Locust; a subprocess proves it still imports.
"""

from __future__ import annotations

import builtins
import io
import random
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from perf import tasks
from perf.receipts import make_batch, make_receipt

from expense_validator.adapters.simulated_classifier import SimulatedClassifier
from expense_validator.app.api import create_app
from tests.support import build_stack

ROOT = Path(__file__).resolve().parents[2]


class LocustLikeClient:
    """What the tasks need from Locust's session: `.post` and `.get` that take `name=`."""

    def __init__(self, http: TestClient) -> None:
        self.http = http
        self.calls: list[tuple[str, str, int]] = []

    def post(
        self,
        url: str,
        data: str | None = None,
        json: Any = None,
        headers: dict[str, str] | None = None,
        name: str | None = None,
    ) -> Any:
        response = self.http.post(url, content=data, json=json, headers=headers)
        self.calls.append(("POST", name or url, response.status_code))
        return response

    def get(self, url: str, params: dict[str, Any] | None = None, name: str | None = None) -> Any:
        response = self.http.get(url, params=params)
        self.calls.append(("GET", name or url, response.status_code))
        return response


def test_every_task_runs_once_and_succeeds(tmp_path: Path) -> None:
    stack = build_stack(tmp_path)
    client = LocustLikeClient(TestClient(create_app(stack.service)))
    worker = stack.worker(SimulatedClassifier())
    ctx = tasks.UserContext(run_id="t1", rng=random.Random(7))

    for _ in range(6):  # the fifth submission is the one that waits for a person
        tasks.submit_receipt(client, ctx)
    tasks.submit_with_key(client, ctx)
    tasks.submit_batch(client, ctx, rows=5)
    worker.run_once()
    tasks.list_by_updated(client, ctx)
    tasks.read_detail(client, ctx)
    tasks.approve_flagged(client, ctx)

    assert {status for _, _, status in client.calls} <= {200, 202}, client.calls
    names = {name for _, name, _ in client.calls}
    assert {
        "/receipts",
        "/receipts (idempotency key)",
        "/batches (100 rows)",
        "/receipts (list)",
        "/receipts/[id]",
        "/receipts/[id]/actions/approve",
    } <= names
    approvals = [c for c in client.calls if c[1].endswith("/actions/approve")]
    assert approvals and approvals[0][2] == 200  # a flagged receipt was in review


def test_a_run_makes_unique_ids_with_test_employees_and_never_reads_the_dataset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_open = builtins.open

    def guarded(file: Any, *args: Any, **kwargs: Any) -> Any:
        assert "receipts.jsonl" not in str(file), "the load test must not open the dataset"
        return real_open(file, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", guarded)
    monkeypatch.setattr(io, "open", guarded)  # `Path.read_text` goes through `io.open`
    receipts = [make_receipt("run1", n) for n in range(1000)]
    assert len({r["receipt_id"] for r in receipts}) == 1000
    assert all(str(r["employee_id"]).startswith("TEST-") for r in receipts)
    assert all(
        line["line_id"].startswith(r["receipt_id"]) for r in receipts for line in r["line_items"]
    )
    rows = make_batch("run1", 2000, 3).splitlines()
    assert len(rows) == 3 and all("TEST-" in row for row in rows)


def test_the_locustfile_still_imports_in_a_clean_interpreter() -> None:
    done = subprocess.run(
        [sys.executable, "-I", "-c", "import sys; sys.path.insert(0, '.'); import perf.locustfile"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert done.returncode == 0, done.stderr
