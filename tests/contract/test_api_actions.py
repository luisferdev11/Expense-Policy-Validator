"""HTTP contract of the reviewer actions (specs/004-backend-lifecycle/contracts/api.md)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from expense_validator.app.api import create_app
from tests.fakes import BillingClassifier
from tests.support import DESCRIPTION, Stack, build_stack, receipt_json

CATEGORIES = {
    "Lunch A": "food_beverage",
    "Lunch B": "food_beverage",
    DESCRIPTION: "office_supplies",
}
MEAL = {"submitted_expense_type": "Meals - Individual"}


@pytest.fixture
def stack(tmp_path: Path) -> Stack:
    stack = build_stack(tmp_path)
    stack.service.submit(receipt_json("SYN-A", "40", "Lunch A", **MEAL))
    stack.service.submit(receipt_json("SYN-B", "50", "Lunch B", **MEAL))
    stack.service.submit(receipt_json("SYN-U", "12.50", DESCRIPTION, employee_id="E-U"))
    stack.worker(BillingClassifier(CATEGORIES)).run_once()
    return stack


@pytest.fixture
def client(stack: Stack) -> TestClient:
    return TestClient(create_app(stack.service))


def act(client: TestClient, receipt_id: str, action: str, **body: Any):  # type: ignore[no-untyped-def]
    body.setdefault("actor", "alice")
    if "evaluation_version" not in body:
        body["evaluation_version"] = client.get(f"/receipts/{receipt_id}").json()[
            "evaluation_version"
        ]
    return client.post(f"/receipts/{receipt_id}/actions/{action}", json=body)


def test_a_flagged_receipt_offers_all_five_actions(client: TestClient) -> None:
    body = client.get("/receipts/SYN-A").json()
    assert body["state"] == "in_review"
    assert body["allowed_actions"] == [
        "approve",
        "reject",
        "correct-category",
        "request-info",
        "escalate",
    ]


def test_reject_returns_the_updated_receipt_and_the_agreement(client: TestClient) -> None:
    response = act(client, "SYN-A", "reject", note="duplicate of a team lunch")
    assert response.status_code == 200
    body = response.json()
    assert (body["state"], body["agreement"], body["allowed_actions"]) == ("rejected", 1, [])
    events = client.get("/receipts/SYN-A/events").json()["items"]
    assert events[-1]["type"] == "ReceiptRejected" and events[-1]["actor"] == "alice"
    assert events[-1]["payload"]["note"] == "duplicate of a team lunch"


def test_an_override_without_a_reason_code_is_422(client: TestClient) -> None:
    response = act(client, "SYN-A", "approve")
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "reason_required" and "policy_exception_granted" in str(error)
    ok = act(client, "SYN-A", "approve", reason_code="policy_exception_granted")
    assert ok.status_code == 200 and ok.json()["agreement"] == 0


def test_a_stale_version_is_409_and_says_which_is_current(client: TestClient) -> None:
    response = act(client, "SYN-A", "reject", evaluation_version=7)
    assert response.status_code == 409
    error = response.json()["error"]
    assert error["code"] == "stale_evaluation"
    assert error["details"] == {"current_evaluation_version": 1}


def test_an_action_the_state_does_not_allow_is_409_with_what_is_allowed(client: TestClient) -> None:
    response = act(client, "SYN-U", "approve")
    assert response.status_code == 409
    error = response.json()["error"]
    assert error["code"] == "action_not_allowed"
    assert error["details"] == {"state": "auto_approved", "allowed": ["reject"]}


def test_request_information_and_escalate_move_the_receipt(client: TestClient) -> None:
    asked = act(client, "SYN-A", "request-info", question="Who attended?")
    assert asked.json()["state"] == "needs_info"
    escalated = act(client, "SYN-B", "escalate", reason="possible split bill")
    assert escalated.json()["state"] == "compliance"


def test_correcting_a_category_returns_the_new_evaluation_version(client: TestClient) -> None:
    response = act(client, "SYN-A", "correct-category", line_id="SYN-A-L1", category="lodging")
    assert response.status_code == 200
    body = response.json()
    assert body["evaluation_version"] == 2 and body["agreement"] == 0
    assert body["result"]["line_items"][0]["category"] == "lodging"
    types = [e["type"] for e in client.get("/receipts/SYN-A/events").json()["items"]]
    assert "LineCategoryCorrected" in types and "DevCandidateMarked" in types
    detail = client.get("/receipts/SYN-A/revisions/1").json()
    assert [e["version"] for e in detail["evaluations"]] == [1, 2]


def test_an_unknown_category_is_422(client: TestClient) -> None:
    response = act(client, "SYN-A", "correct-category", line_id="SYN-A-L1", category="spaceship")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "unknown_category"


def test_unknown_receipts_and_actions_are_404(client: TestClient) -> None:
    assert act(client, "NOPE", "reject", evaluation_version=1).status_code == 404
    assert act(client, "SYN-A", "levitate").status_code == 404
    assert act(client, "SYN-A", "levitate").json()["error"]["code"] == "not_found"


def test_a_malformed_body_is_422_with_the_fields(client: TestClient) -> None:
    missing = client.post("/receipts/SYN-A/actions/reject", json={"actor": "alice"})
    assert missing.status_code == 422
    assert missing.json()["error"]["code"] == "invalid_request"
    assert "evaluation_version" in str(missing.json()["error"]["details"])
    extra = client.post(
        "/receipts/SYN-A/actions/reject",
        json={"actor": "a", "evaluation_version": 1, "labels": {"disposition": "pass"}},
    )
    assert extra.status_code == 422  # unknown fields are refused, answer keys included
    blank = act(client, "SYN-A", "reject", actor=" ")
    assert blank.status_code == 422 and blank.json()["error"]["code"] == "invalid_action"
