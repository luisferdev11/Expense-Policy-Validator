"""The tasks a simulated user performs (spec 006, research R14), as plain functions.

They take any client with Locust's `.post` and `.get` (both accept `name=`, which groups the
statistics), so a test can run each one against the real app without Locust. This module never
imports Locust: Locust patches the standard library on import, which must not happen in the
test run. `perf/locustfile.py` wires these functions into Locust users.
"""

from __future__ import annotations

import itertools
import json
import random
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any, Protocol

from perf.profiles import BATCH_ROWS
from perf.receipts import is_flagged, make_batch, make_receipt

JSON = {"Content-Type": "application/json"}
NDJSON = {"Content-Type": "application/x-ndjson"}
ACTOR = "load-test"


class Client(Protocol):
    def post(
        self,
        url: str,
        data: str | None = None,
        json: Any = None,
        headers: dict[str, str] | None = None,
        name: str | None = None,
    ) -> Any: ...

    def get(
        self, url: str, params: dict[str, Any] | None = None, name: str | None = None
    ) -> Any: ...


@dataclass
class UserContext:
    """One simulated user: the run it belongs to, a source of receipt numbers shared by the run
    (so ids never repeat across users), and the receipts it has submitted."""

    run_id: str
    rng: random.Random
    numbers: Iterator[int] = field(default_factory=lambda: itertools.count(1))
    submitted: list[str] = field(default_factory=list)
    flagged: list[str] = field(default_factory=list)  # submitted and waiting for a person


def _accepted(response: Any) -> bool:
    return bool(response.status_code in (200, 202))


def submit_receipt(client: Client, ctx: UserContext) -> None:
    n = next(ctx.numbers)
    body = make_receipt(ctx.run_id, n)
    response = client.post("/receipts", data=json.dumps(body), headers=JSON, name="/receipts")
    if _accepted(response):
        ctx.submitted.append(body["receipt_id"])
        if is_flagged(n):
            ctx.flagged.append(body["receipt_id"])


def submit_with_key(client: Client, ctx: UserContext) -> None:
    n = next(ctx.numbers)
    body = make_receipt(ctx.run_id, n)
    headers = {**JSON, "Idempotency-Key": f"lt-{ctx.run_id}-{n:06d}"}
    response = client.post(
        "/receipts", data=json.dumps(body), headers=headers, name="/receipts (idempotency key)"
    )
    if _accepted(response):
        ctx.submitted.append(body["receipt_id"])
        if is_flagged(n):
            ctx.flagged.append(body["receipt_id"])


def submit_batch(client: Client, ctx: UserContext, rows: int = BATCH_ROWS) -> None:
    start = next(ctx.numbers)
    for _ in range(rows - 1):  # take the numbers the rows use
        next(ctx.numbers)
    client.post(
        "/batches",
        data=make_batch(ctx.run_id, start, rows),
        headers=NDJSON,
        name="/batches (100 rows)",
    )


def list_by_updated(client: Client, ctx: UserContext) -> None:
    client.get("/receipts", params={"order": "updated_at", "limit": 20}, name="/receipts (list)")


def read_detail(client: Client, ctx: UserContext) -> None:
    if not ctx.submitted:
        return
    client.get(f"/receipts/{ctx.rng.choice(ctx.submitted)}", name="/receipts/[id]")


def approve_flagged(client: Client, ctx: UserContext) -> None:
    """Approve the oldest receipt this user submitted that waits for a person, once it does."""
    if not ctx.flagged:
        return
    receipt_id = ctx.flagged[0]
    response = client.get(f"/receipts/{receipt_id}", name="/receipts/[id]")
    if response.status_code != 200:
        return
    detail = response.json()
    if detail["state"] != "in_review":
        if detail["state"] not in ("submitted", "classifying"):
            ctx.flagged.pop(0)  # it went somewhere else; stop waiting for it
        return
    ctx.flagged.pop(0)
    client.post(
        f"/receipts/{receipt_id}/actions/approve",
        data=json.dumps(
            {
                "actor": ACTOR,
                "evaluation_version": detail["evaluation_version"],
                "reason_code": "policy_exception_granted",
            }
        ),
        headers=JSON,
        name="/receipts/[id]/actions/approve",
    )
