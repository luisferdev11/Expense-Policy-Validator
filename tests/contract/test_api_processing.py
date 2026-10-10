"""HTTP contract of a receipt that has been processed, failed or retried (contracts/api.md)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from expense_validator.app.api import create_app
from tests.support import Stack, build_stack, notebook_classifier, receipt_json


@pytest.fixture
def stack(tmp_path: Path) -> Stack:
    return build_stack(tmp_path)


@pytest.fixture
def client(stack: Stack) -> TestClient:
    return TestClient(create_app(stack.service))


def submit(client: TestClient) -> None:
    client.post("/receipts", content=receipt_json(), headers={"Content-Type": "application/json"})


def test_a_processed_receipt_shows_its_result_state_and_allowed_actions(
    stack: Stack, client: TestClient
) -> None:
    submit(client)
    stack.worker(notebook_classifier()).run_once()
    body = client.get("/receipts/SYN-1").json()
    assert body["evaluation_version"] == 1 and body["result"]["receipt_id"] == "SYN-1"
    assert body["result"]["run"]["model_id"] == "fake-model"
    assert body["state"] == "auto_approved" and body["allowed_actions"] == ["reject"]
    types = [e["type"] for e in client.get("/receipts/SYN-1/events").json()["items"]]
    assert types == ["ReceiptSubmitted", "ReceiptClassified", "ReceiptEvaluated"]
    revision = client.get("/receipts/SYN-1/revisions/1").json()
    assert [e["version"] for e in revision["evaluations"]] == [1]


def test_a_failed_receipt_reports_its_stage_and_can_be_retried(
    stack: Stack, client: TestClient
) -> None:
    submit(client)
    stack.worker(notebook_classifier(fail_with=RuntimeError("gateway down"))).run_once()
    failed = client.get("/receipts/SYN-1").json()
    assert failed["state"] == "failed"
    assert failed["failed"] == {"stage": "classify", "reason": "RuntimeError: gateway down"}

    retried = client.post("/receipts/SYN-1/retry")
    assert retried.status_code == 202 and retried.json()["state"] == "submitted"
    assert client.post("/receipts/SYN-1/retry").status_code == 409

    stack.worker(notebook_classifier()).run_once()
    assert client.get("/receipts/SYN-1").json()["failed"] is None


def test_retrying_what_is_not_failed_is_409_and_unknown_is_404(client: TestClient) -> None:
    submit(client)
    conflict = client.post("/receipts/SYN-1/retry")
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "action_not_allowed"
    assert client.post("/receipts/NOPE/retry").status_code == 404


def test_the_list_can_be_filtered_by_state_and_disposition(
    stack: Stack, client: TestClient
) -> None:
    submit(client)
    assert client.get("/receipts", params={"state": "submitted"}).json()["total"] == 1
    stack.worker(notebook_classifier()).run_once()
    assert client.get("/receipts", params={"state": "submitted"}).json()["total"] == 0
    done = client.get("/receipts", params={"disposition": "pass"}).json()
    assert [i["receipt_id"] for i in done["items"]] == ["SYN-1"]
