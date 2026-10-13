"""One timestamp format for the whole store (spec 006, research R7)."""

from __future__ import annotations

import os
import random
import time
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta, timezone

import pytest

from expense_validator.ports.store import stamp


@pytest.fixture
def local_zone_is_not_utc() -> Iterator[None]:
    """Run with a machine zone that is not UTC, so a naive value cannot pass by luck."""
    previous = os.environ.get("TZ")
    os.environ["TZ"] = "America/Mexico_City"
    time.tzset()
    yield
    if previous is None:
        del os.environ["TZ"]
    else:
        os.environ["TZ"] = previous
    time.tzset()


def test_an_aware_utc_value_has_microseconds_and_the_offset() -> None:
    text = stamp(datetime(2026, 10, 12, 15, 4, 5, 123456, tzinfo=UTC))
    assert text == "2026-10-12T15:04:05.123456+00:00"
    assert len(text) == 32


def test_a_zero_microsecond_value_keeps_the_same_width() -> None:
    text = stamp(datetime(2026, 10, 12, 15, 0, tzinfo=UTC))
    assert text == "2026-10-12T15:00:00.000000+00:00"
    assert len(text) == 32


def test_an_aware_value_in_another_zone_is_converted_to_utc() -> None:
    plus_two = timezone(timedelta(hours=2))
    assert (
        stamp(datetime(2026, 10, 12, 17, 0, tzinfo=plus_two)) == "2026-10-12T15:00:00.000000+00:00"
    )


@pytest.mark.usefixtures("local_zone_is_not_utc")
def test_a_naive_value_is_taken_as_utc_whatever_the_machine_zone() -> None:
    assert stamp(datetime(2026, 10, 12, 15, 0)) == "2026-10-12T15:00:00.000000+00:00"


def test_text_order_equals_time_order() -> None:
    rng = random.Random(20261012)
    base = datetime(2026, 1, 1, tzinfo=UTC)
    moments = [base + timedelta(microseconds=rng.randrange(0, 10**13)) for _ in range(100)]
    # some on whole seconds, which `isoformat()` alone would print shorter
    moments += [base + timedelta(seconds=rng.randrange(0, 10**7)) for _ in range(20)]
    assert sorted(moments) == [m for _, m in sorted((stamp(m), m) for m in moments)]
