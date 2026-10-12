"""The load profiles (spec 006, research R14), in one place for the locustfile and the report.

Rates are receipts submitted per second. Locust runs a fixed number of users, each doing one task
at a time; `user_wait_seconds` turns a target rate into the pause between a user's tasks, from the
mix of tasks, so a profile reads as "1.2 receipts a second" and not as a user count.
"""

from __future__ import annotations

from dataclasses import dataclass

# Weights of the tasks a simulated user mixes (research R14).
WEIGHTS: dict[str, float] = {
    "submit": 5.0,
    "submit_key": 1.0,
    "batch": 0.1,
    "list": 3.0,
    "detail": 3.0,
    "approve": 0.5,
}
BATCH_ROWS = 100

# Reported, not enforced (research R14).
READ_P95_MS = 300
SUBMIT_P95_MS = 500
DRAIN_OK_SECONDS = 60.0


@dataclass(frozen=True)
class Profile:
    name: str
    users: int
    spawn_rate: float  # users started per second
    run_time_s: int
    receipts_per_s: float
    classifier: str  # openrouter, keyword or simulated
    latency_ms: int  # simulated latency per line
    workers: int  # worker processes beside the API (one is the in-process thread)
    batches: bool  # whether the batch task runs (it would bill a model in `live`)
    purpose: str


PROFILES: dict[str, Profile] = {
    "smoke": Profile(
        "smoke", 5, 5, 30, 1.0, "simulated", 0, 1, True, "the setup works; under 2 minutes"
    ),
    "nominal": Profile(
        "nominal", 10, 2, 300, 1.2, "simulated", 1500, 5, True, "100,000 receipts a day on average"
    ),
    "peak": Profile(
        "peak", 60, 10, 300, 12.0, "simulated", 1500, 10, True, "ten times the nominal rate"
    ),
    "live": Profile(
        "live", 2, 1, 120, 0.2, "openrouter", 0, 1, False, "real latency and rate limits, capped"
    ),
}


def weights(profile: Profile) -> dict[str, float]:
    return {k: (0.0 if k == "batch" and not profile.batches else v) for k, v in WEIGHTS.items()}


def receipts_per_task(profile: Profile) -> float:
    """Receipts one task submits on average, given the mix (a batch task sends BATCH_ROWS)."""
    w = weights(profile)
    return (w["submit"] + w["submit_key"] + w["batch"] * BATCH_ROWS) / sum(w.values())


def user_wait_seconds(profile: Profile) -> float:
    """Pause between one user's tasks so that all users together submit `receipts_per_s`."""
    tasks_per_second = profile.receipts_per_s / receipts_per_task(profile)
    return profile.users / tasks_per_second


def kind(method: str, name: str) -> str:
    """Which threshold an endpoint falls under: a submit, a read, or neither."""
    if method == "POST" and name in ("/receipts", "/receipts (idempotency key)"):
        return "submit"
    if method == "GET":
        return "read"
    return "other"
