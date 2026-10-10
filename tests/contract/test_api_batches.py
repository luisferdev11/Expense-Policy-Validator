"""HTTP contract of the batch endpoints (specs/004-backend-lifecycle/contracts/api.md)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from expense_validator.app.api import create_app
from tests.support import Stack, build_stack, notebook_classifier, receipt_json

NDJSON = {"Content-Type": "application/x-ndjson"}


@pytest.fixture
def stack(tmp_path: Path) -> Stack:
    return build_stack(tmp_path)


@pytest.fixture
def client(stack: Stack) -> TestClient:
    return TestClient(create_app(stack.service))


def ndjson(*rows: str) -> str:
    return "\n".join(rows) + "\n"


def test_a_clean_jsonl_batch_is_202_with_one_item_per_row(client: TestClient) -> None:
    response = client.post(
        "/batches", content=ndjson(receipt_json("SYN-1"), receipt_json("SYN-2")), headers=NDJSON
    )
    assert response.status_code == 202
    body = response.json()
    assert body["batch_id"].startswith("bat_") and body["total"] == 2
    assert body["counts"] == {"submitted": 2}
    assert [(i["row"], i["receipt_id"], i["outcome"]) for i in body["items"]] == [
        (1, "SYN-1", "accepted"),
        (2, "SYN-2", "accepted"),
    ]


def test_a_batch_with_a_bad_row_is_207_and_names_the_row(client: TestClient) -> None:
    text = ndjson(receipt_json("SYN-1"), "{broken", receipt_json("SYN-2"))
    response = client.post("/batches", content=text, headers=NDJSON)
    assert response.status_code == 207
    items = response.json()["items"]
    assert [i["outcome"] for i in items] == ["accepted", "invalid", "accepted"]
    assert items[1]["row"] == 2 and "not valid JSON" in items[1]["error"]
    assert client.get("/receipts").json()["total"] == 2


def test_a_json_array_body_is_accepted(client: TestClient) -> None:
    rows = [json.loads(receipt_json("SYN-1")), json.loads(receipt_json("SYN-2"))]
    response = client.post("/batches", json=rows)
    assert response.status_code == 202 and response.json()["total"] == 2


def test_the_same_batch_again_reports_every_receipt_as_existing(client: TestClient) -> None:
    text = ndjson(receipt_json("SYN-1"), receipt_json("SYN-2"))
    client.post("/batches", content=text, headers=NDJSON)
    again = client.post("/batches", content=text, headers=NDJSON)
    assert again.status_code == 202
    assert [i["outcome"] for i in again.json()["items"]] == ["existing", "existing"]


def test_the_batch_summary_follows_processing(stack: Stack, client: TestClient) -> None:
    created = client.post(
        "/batches", content=ndjson(receipt_json("SYN-1"), receipt_json("SYN-2")), headers=NDJSON
    ).json()
    stack.worker(notebook_classifier()).run_once()
    summary = client.get(f"/batches/{created['batch_id']}").json()
    assert summary["counts"] == {"auto_approved": 2}
    assert [i["state"] for i in summary["items"]] == ["auto_approved", "auto_approved"]
    listed = client.get("/receipts", params={"batch_id": created["batch_id"]}).json()
    assert listed["total"] == 2


def test_an_unknown_batch_is_404_and_an_empty_one_is_422(client: TestClient) -> None:
    assert client.get("/batches/bat_nope").status_code == 404
    empty = client.post("/batches", content="  \n", headers=NDJSON)
    assert empty.status_code == 422 and empty.json()["error"]["code"] == "invalid_batch"


def test_the_openapi_document_lists_the_batch_endpoints(client: TestClient) -> None:
    paths = client.get("/openapi.json").json()["paths"]
    assert {"/batches", "/batches/{batch_id}", "/receipts/{receipt_id}/actions/{action}"} <= set(
        paths
    )
