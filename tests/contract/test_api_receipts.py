"""HTTP contract of the receipt endpoints (specs/004-backend-lifecycle/contracts/api.md)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from expense_validator.adapters.sqlite_store import SqliteStore
from expense_validator.app.api import create_app
from expense_validator.app.service import ReceiptService
from tests.fakes import StepClock
from tests.support import FIXTURE
from tests.support import receipt_json as raw


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    store = SqliteStore(tmp_path / "epv.sqlite3")
    return TestClient(create_app(ReceiptService(store, StepClock())))


def post(client: TestClient, body: str, key: str | None = None):  # type: ignore[no-untyped-def]
    headers = {"Content-Type": "application/json"}
    if key is not None:
        headers["Idempotency-Key"] = key
    return client.post("/receipts", content=body, headers=headers)


def test_health_reports_the_schema_version(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "schema_version": 1}


def test_a_new_receipt_is_accepted_with_202(client: TestClient) -> None:
    response = post(client, raw())
    assert response.status_code == 202
    assert response.json() == {
        "receipt_id": "SYN-1",
        "revision": 1,
        "outcome": "accepted",
        "state": "submitted",
        "superseded": False,
    }


def test_the_same_receipt_again_is_200_existing(client: TestClient) -> None:
    post(client, raw())
    response = post(client, raw())
    assert response.status_code == 200
    assert response.json()["outcome"] == "existing"


def test_a_changed_receipt_is_a_new_revision_with_202(client: TestClient) -> None:
    post(client, raw())
    response = post(client, raw(amount="99.00"))
    assert response.status_code == 202
    assert (response.json()["outcome"], response.json()["revision"]) == ("revision", 2)


def test_a_reused_client_key_with_another_body_is_422(client: TestClient) -> None:
    post(client, raw(), key="k1")
    response = post(client, raw(amount="99.00"), key="k1")
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "idempotency_key_reuse"
    assert error["details"] == {"idempotency_key": "k1"}


def test_an_invalid_body_is_422_and_names_the_fields(client: TestClient) -> None:
    response = post(client, '{"receipt_id": "X"}')
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "invalid_receipt" and "employee_id" in error["details"]["fields"]
    assert client.get("/receipts").json()["total"] == 0


def test_invalid_json_and_an_overlong_key_are_422(client: TestClient) -> None:
    assert post(client, "{nope").json()["error"]["code"] == "invalid_receipt"
    assert post(client, raw(), key="k" * 300).json()["error"]["code"] == "invalid_idempotency_key"


def test_get_a_receipt_returns_the_stripped_receipt_and_no_result_yet(client: TestClient) -> None:
    post(client, FIXTURE.read_text(encoding="utf-8"))
    response = client.get("/receipts/SYN-FIREWALL")
    assert response.status_code == 200
    body = response.json()
    assert body["state"] == "submitted" and body["revision"] == 1
    assert body["result"] is None and body["allowed_actions"] == [] and body["failed"] is None
    assert body["receipt"]["receipt_id"] == "SYN-FIREWALL"
    assert "labels" not in json.dumps(body) and "notes" not in json.dumps(body)


def test_money_keeps_its_written_precision(client: TestClient) -> None:
    post(client, raw(amount="12.10"))
    body = client.get("/receipts/SYN-1").json()
    assert body["receipt"]["total_amount"] == "12.10"


def test_an_unknown_receipt_is_404_with_the_error_shape(client: TestClient) -> None:
    for path in ("/receipts/NOPE", "/receipts/NOPE/events", "/receipts/NOPE/revisions/1"):
        response = client.get(path)
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"


def test_the_event_trail_is_in_order(client: TestClient) -> None:
    post(client, raw())
    post(client, raw(amount="99.00"))
    items = client.get("/receipts/SYN-1/events").json()["items"]
    assert [i["type"] for i in items] == [
        "ReceiptSubmitted",
        "RevisionSuperseded",
        "ReceiptSubmitted",
    ]
    assert [i["seq"] for i in items] == sorted(i["seq"] for i in items)
    assert items[0]["actor"] == "system" and items[0]["payload"]["idempotency_key"]


def test_a_revision_can_be_read_after_it_is_superseded(client: TestClient) -> None:
    post(client, raw())
    post(client, raw(amount="99.00"))
    first = client.get("/receipts/SYN-1/revisions/1").json()
    assert first["status"] == "superseded" and first["receipt"]["total_amount"] == "12.50"
    assert first["evaluations"] == []
    assert client.get("/receipts/SYN-1/revisions/9").status_code == 404


def test_the_list_filters_and_paginates(client: TestClient) -> None:
    for n in range(3):
        post(client, raw(receipt_id=f"SYN-{n}"))
    everything = client.get("/receipts").json()
    assert everything["total"] == 3 and len(everything["items"]) == 3
    page = client.get("/receipts", params={"limit": 2, "offset": 2}).json()
    assert page["total"] == 3 and [i["receipt_id"] for i in page["items"]] == ["SYN-2"]
    assert client.get("/receipts", params={"state": "approved"}).json()["total"] == 0
    assert client.get("/receipts", params={"limit": 0}).status_code == 422


def test_unknown_routes_and_methods_use_the_error_shape(client: TestClient) -> None:
    assert client.get("/nope").json()["error"]["code"] == "not_found"
    assert client.put("/receipts").json()["error"]["code"] == "method_not_allowed"


def test_the_openapi_document_lists_every_receipt_endpoint(client: TestClient) -> None:
    paths = client.get("/openapi.json").json()["paths"]
    assert {"/receipts", "/receipts/{receipt_id}", "/receipts/{receipt_id}/events"} <= set(paths)
