"""Sharing keys that tell which receipts a change can affect (ADR 0007 D6, research R4)."""

from __future__ import annotations

from datetime import datetime

from expense_validator.domain.cascade import sharing_keys
from expense_validator.domain.engine.context import day_key
from tests.factories import receipt


def test_a_receipt_shares_its_employee_day_and_its_trip() -> None:
    r = receipt(employee_id="E-7", trip_id="TRIP-1", transaction_datetime="2026-05-01T12:00:00")
    assert sharing_keys(r) == frozenset(
        {f"day:{day_key('E-7', datetime(2026, 5, 1, 12))}", "trip:TRIP-1"}
    )


def test_the_day_key_is_the_one_the_engine_uses() -> None:
    r = receipt(employee_id="E-7", transaction_datetime="2026-05-01T23:59:00")
    assert sharing_keys(r) == frozenset({"day:E-7|2026-05-01"})


def test_a_receipt_without_a_date_or_a_trip_shares_nothing() -> None:
    assert sharing_keys(receipt(transaction_datetime=None, trip_id=None)) == frozenset()


def test_two_employees_on_the_same_day_share_nothing() -> None:
    a = receipt(receipt_id="A", employee_id="E-1")
    b = receipt(receipt_id="B", employee_id="E-2")
    assert sharing_keys(a).isdisjoint(sharing_keys(b))
