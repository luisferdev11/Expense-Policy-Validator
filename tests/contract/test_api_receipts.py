"""HTTP contract of the receipt endpoints (specs/004-backend-lifecycle/contracts/api.md)."""

from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from expense_validator.adapters.keyword_classifier import KeywordClassifier
from expense_validator.adapters.sqlite_store import SqliteStore
from expense_validator.app.api import create_app
from expense_validator.app.service import ReceiptService
from expense_validator.domain.models import LineItemInput, ReceiptInput, ReceiptResult
from tests.fakes import StepClock
from tests.support import FIXTURE, build_stack
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
    assert response.json() == {"status": "ok", "schema_version": 2}


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


def test_summary_and_detail_carry_created_at_in_the_one_timestamp_format(
    client: TestClient,
) -> None:
    post(client, raw())
    summary = client.get("/receipts").json()["items"][0]
    detail = client.get("/receipts/SYN-1").json()
    assert summary["created_at"] == detail["created_at"]
    assert len(summary["created_at"]) == len(summary["updated_at"]) == 32
    assert summary["created_at"].endswith("+00:00")


def test_created_at_stays_when_a_revision_arrives_and_updated_at_moves(
    tmp_path: Path,
) -> None:
    clock = StepClock(step=timedelta(0))
    app = create_app(ReceiptService(SqliteStore(tmp_path / "epv.sqlite3"), clock))
    client = TestClient(app)
    post(client, raw())
    clock.advance(timedelta(seconds=60))
    post(client, raw(amount="99.00"))
    body = client.get("/receipts/SYN-1").json()
    assert body["revision"] == 2
    assert body["created_at"] == "2026-10-10T12:00:00.000000+00:00"
    assert body["updated_at"] == "2026-10-10T12:01:00.000000+00:00"
    assert client.get("/receipts/SYN-1/revisions/2").json()["created_at"] == body["updated_at"]


def test_the_list_orders_by_created_at_or_updated_at(tmp_path: Path) -> None:
    clock = StepClock(step=timedelta(seconds=1))
    client = TestClient(create_app(ReceiptService(SqliteStore(tmp_path / "epv.sqlite3"), clock)))
    for rid in ("SYN-B", "SYN-A", "SYN-C"):
        post(client, raw(receipt_id=rid))
    post(client, raw(receipt_id="SYN-B", amount="99.00"))  # B is updated last

    def ids(order: str | None) -> list[str]:
        params = {} if order is None else {"order": order}
        return [i["receipt_id"] for i in client.get("/receipts", params=params).json()["items"]]

    assert ids(None) == ids("receipt_id") == ["SYN-A", "SYN-B", "SYN-C"]
    assert ids("created_at") == ["SYN-B", "SYN-A", "SYN-C"]
    assert ids("updated_at") == ["SYN-A", "SYN-C", "SYN-B"]


def test_an_unknown_order_is_a_422_in_the_error_shape(client: TestClient) -> None:
    response = client.get("/receipts", params={"order": "bogus"})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_request"


def test_unknown_routes_and_methods_use_the_error_shape(client: TestClient) -> None:
    assert client.get("/nope").json()["error"]["code"] == "not_found"
    assert client.put("/receipts").json()["error"]["code"] == "method_not_allowed"


def test_the_openapi_document_lists_every_receipt_endpoint(client: TestClient) -> None:
    paths = client.get("/openapi.json").json()["paths"]
    assert {"/receipts", "/receipts/{receipt_id}", "/receipts/{receipt_id}/events"} <= set(paths)


# The typed OpenAPI document (spec 006, US4)


def _schema(client: TestClient, name: str) -> dict[str, Any]:
    components = client.get("/openapi.json").json()["components"]["schemas"]
    assert name in components, f"component {name} is missing"
    return components[name]  # type: ignore[no-any-return]


def _ref(node: dict[str, Any]) -> str | None:
    """The component a property points at, directly or on the non-null side of an anyOf."""
    for candidate in [node, *node.get("anyOf", [])]:
        if "$ref" in candidate:
            return str(candidate["$ref"]).rsplit("/", 1)[1]
    return None


def _is_string(node: dict[str, Any]) -> bool:
    return node.get("type") == "string" or any(
        alt.get("type") == "string" for alt in node.get("anyOf", [])
    )


def test_receipts_and_results_are_typed_in_the_document(client: TestClient) -> None:
    detail = _schema(client, "ReceiptDetail")["properties"]
    assert _ref(detail["receipt"]) == "ReceiptInput"
    assert _ref(detail["result"]) == "ReceiptResult"
    assert _ref(_schema(client, "RevisionDetail")["properties"]["receipt"]) == "ReceiptInput"
    assert _ref(_schema(client, "EvaluationItem")["properties"]["result"]) == "ReceiptResult"
    assert _ref(_schema(client, "ActionResponse")["properties"]["receipt"]) == "ReceiptInput"


def test_every_model_field_is_in_the_typed_schemas_and_money_is_a_string(
    client: TestClient,
) -> None:
    receipt_schema = _schema(client, "ReceiptInput")
    assert set(receipt_schema["properties"]) == set(ReceiptInput.model_fields)
    line_schema = _schema(client, "LineItemInput")
    assert set(line_schema["properties"]) == set(LineItemInput.model_fields)
    result_schema = _schema(client, "ReceiptResult")
    assert set(result_schema["properties"]) == set(ReceiptResult.model_fields)
    for name in ("fx_rate_to_usd", "total_amount", "total_amount_usd"):
        assert _is_string(receipt_schema["properties"][name]), name
    for name in ("quantity", "unit_price", "amount", "amount_usd"):
        assert _is_string(line_schema["properties"][name]), name


def test_the_request_and_response_schemas_are_separate_components(client: TestClient) -> None:
    document = client.get("/openapi.json").json()
    names = set(document["components"]["schemas"])
    assert {
        "ReceiptInput",
        "LineItemInput",
        "ReceiptResult",
        "ReceiptInputRequest",
        "LineItemInputRequest",
    } <= names
    assert not [n for n in names if n.endswith(("-Input", "-Output"))]
    assert _schema(client, "ReceiptInputRequest") != _schema(client, "ReceiptInput")
    assert _schema(client, "LineItemInputRequest") != _schema(client, "LineItemInput")
    body = document["paths"]["/receipts"]["post"]["requestBody"]["content"]["application/json"]
    assert body["schema"] == {"$ref": "#/components/schemas/ReceiptInputRequest"}


def test_typing_the_document_left_the_wire_format_byte_for_byte_as_it_was(tmp_path: Path) -> None:
    """The detail and the revision of the sample receipt DEMO-001, captured before the schemas were
    typed (`wire_before_typing.json`), are exactly what the API still sends."""
    expected = json.loads((FIXTURE.parent / "wire_before_typing.json").read_text(encoding="utf-8"))
    stack = build_stack(tmp_path)
    sample = Path(__file__).resolve().parents[2] / "docs" / "samples" / "receipt-one.json"
    stack.service.submit(sample.read_text(encoding="utf-8"))
    stack.worker(KeywordClassifier()).run_once()
    live = TestClient(create_app(stack.service))
    assert live.get("/receipts/DEMO-001").text == expected["detail"]
    assert live.get("/receipts/DEMO-001/revisions/1").text == expected["revision"]
