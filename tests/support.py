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
from expense_validator.app.reviewing import ActionRequest, ReviewService
from expense_validator.app.service import ReceiptService
from expense_validator.app.worker import Worker
from expense_validator.ports.classifier import ItemClassifier
from expense_validator.ports.tracer import Tracer
from tests.fakes import BillingClassifier, RecordingTracer, StepClock

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


REVIEW_CATEGORIES = {
    "Lunch A": "food_beverage",
    "Lunch B": "food_beverage",
    DESCRIPTION: "office_supplies",
    "Gift basket": "gift",
}
REVIEW_RECIPIENTS = {"Gift basket": ("government_official", "Vice-Minister")}
MEAL = {"submitted_expense_type": "Meals - Individual"}


class ReviewEnv:
    """Receipts in every resting state, a worker, and the review service, on one store.

    SYN-A and SYN-B are two lunches of one employee-day, 40 + 50 > 75 (MEAL-01, flag, so
    `in_review`). SYN-U is a notebook (pass, so `auto_approved`). SYN-G is a gift for a
    government official (GIFT-04, critical, so `compliance`).
    """

    def __init__(self, tmp_path: Path) -> None:
        self.tracer = RecordingTracer()
        self.stack: Stack = build_stack(tmp_path, self.tracer)
        self.service = self.stack.service
        self.review = ReviewService(
            self.stack.store, self.stack.clock, self.service, tracer=self.tracer
        )
        self.worker = self.stack.worker(
            BillingClassifier(REVIEW_CATEGORIES, recipients=REVIEW_RECIPIENTS), self.tracer
        )

    def submit(self, receipt_id: str, amount: str, description: str, **fields: object) -> None:
        self.service.submit(receipt_json(receipt_id, amount, description, **fields))

    def seed(self) -> None:
        self.submit("SYN-A", "40", "Lunch A", **MEAL)
        self.submit("SYN-B", "50", "Lunch B", **MEAL)
        self.submit("SYN-U", "12.50", DESCRIPTION, employee_id="E-U")
        self.submit("SYN-G", "30", "Gift basket", employee_id="E-G")
        self.worker.run_once()

    def act(self, receipt_id: str, action: Any, **fields: Any) -> Any:
        view = self.service.get_receipt(receipt_id)
        fields.setdefault("actor", "alice")
        fields.setdefault("evaluation_version", view.record.evaluation_version)
        return self.review.act(receipt_id, action, ActionRequest(**fields))

    def state(self, receipt_id: str) -> str:
        return self.service.get_receipt(receipt_id).record.state

    def events(self, receipt_id: str) -> list[Any]:
        return [e.event for e in self.service.list_events(receipt_id)]
