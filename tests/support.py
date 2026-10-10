"""Shared setup for the backend tests: receipt JSON and a store, service and worker stack.

Every value is invented. Nothing is read from the answer fields.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from expense_validator.adapters.config_files import load_settings
from expense_validator.adapters.sqlite_store import SqliteStore
from expense_validator.adapters.tracing import NoopTracer
from expense_validator.app.service import ReceiptService
from expense_validator.app.worker import Worker
from expense_validator.ports.classifier import ItemClassifier
from expense_validator.ports.tracer import Tracer
from tests.fakes import BillingClassifier, StepClock

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "receipt_with_answers.json"
DESCRIPTION = "Spiral notebook"


def receipt_json(
    receipt_id: str = "SYN-1",
    amount: str = "12.50",
    description: str = DESCRIPTION,
    **overrides: Any,
) -> str:
    body: dict[str, Any] = {
        "receipt_id": receipt_id,
        "employee_id": "E-1",
        "employee_country": "US",
        "entity": "GLOBAL",
        "submitted_expense_type": "Office Supplies",
        "merchant_name": "Synthetic Merchant",
        "mcc": 5943,
        "mcc_description": "Office and stationery supply",
        "transaction_datetime": "2026-05-01T12:00:00",
        "currency": "USD",
        "fx_rate_to_usd": 1.0,
        "total_amount": amount,
        "total_amount_usd": amount,
        "attendee_count": None,
        "trip_id": None,
        "trip_nights": None,
        "pre_approval_ref": None,
        "itemized": True,
        "line_items": [
            {
                "line_id": f"{receipt_id}-L1",
                "description_raw": description,
                "language": "en",
                "quantity": 1,
                "unit_price": amount,
                "amount": amount,
                "amount_usd": amount,
            }
        ],
    }
    body.update(overrides)
    return json.dumps(body)


@dataclass
class Stack:
    store: SqliteStore
    service: ReceiptService
    clock: StepClock
    tracer: Tracer

    def worker(
        self, classifier: ItemClassifier, tracer: Tracer | None = None, **kwargs: Any
    ) -> Worker:
        return Worker(
            self.store,
            classifier,
            tracer or self.tracer,
            load_settings(),
            self.clock,
            **kwargs,
        )


def build_stack(tmp_path: Path, tracer: Tracer | None = None) -> Stack:
    clock = StepClock()
    store = SqliteStore(tmp_path / "epv.sqlite3")
    return Stack(store, ReceiptService(store, clock), clock, tracer or NoopTracer())


def notebook_classifier(**kwargs: Any) -> BillingClassifier:
    """A classifier that knows the default test description."""
    return BillingClassifier({DESCRIPTION: "office_supplies"}, **kwargs)
