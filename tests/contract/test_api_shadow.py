"""GET /receipts/{id}/shadow (specs/007-jev-classifier/contracts/api-delta.md)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from expense_validator.app.api import create_app
from expense_validator.app.composition import openapi_document
from tests.fakes import BillingClassifier
from tests.support import DESCRIPTION, Stack, build_stack, notebook_classifier, receipt_json


@pytest.fixture
def stack(tmp_path: Path) -> Stack:
    return build_stack(tmp_path)


def client_of(stack: Stack) -> TestClient:
    return TestClient(create_app(stack.service))


def run_with_shadow(stack: Stack, shadow: BillingClassifier, name: str = "jev-hybrid") -> None:
    stack.service.submit(receipt_json())
    stack.worker(notebook_classifier(), shadow=shadow, shadow_name=name).run_once()


def test_a_receipt_with_shadow_rows_shows_both_answers_side_by_side(stack: Stack) -> None:
    run_with_shadow(stack, BillingClassifier({DESCRIPTION: "tobacco"}))
    response = client_of(stack).get("/receipts/SYN-1/shadow")
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {
        "receipt_id",
        "revision",
        "primary",
        "shadow",
        "lines",
        "summary",
        "created_at",
    }
    assert (body["receipt_id"], body["revision"]) == ("SYN-1", 1)
    assert body["primary"] == {
        "classifier": "hand",
        "model_id": "hand-written",
        "prompt_version": "test",
    }
    assert body["shadow"] == {
        "classifier": "jev-hybrid",
        "model_id": "fake-model",
        "prompt_version": "test",
    }
    (line,) = body["lines"]
    assert set(line) == {"line_id", "primary", "shadow", "agrees_category", "agrees_all"}
    assert line["line_id"] == "SYN-1-L1"
    answer = {
        "status",
        "category",
        "confidence",
        "subtype",
        "recipient_kind",
        "recipient_name",
        "unclassified_reason",
    }
    assert set(line["primary"]) == set(line["shadow"]) == answer
    assert (line["primary"]["category"], line["shadow"]["category"]) == (
        "office_supplies",
        "tobacco",
    )
    assert (line["agrees_category"], line["agrees_all"]) == (False, False)
    assert body["summary"] == {"lines": 1, "comparable": 1, "agree_category": 0, "agree_all": 0}
    assert len(body["created_at"]) == 32 and body["created_at"].endswith("+00:00")


def test_a_shadow_that_agrees_is_counted_as_agreeing(stack: Stack) -> None:
    run_with_shadow(stack, BillingClassifier({DESCRIPTION: "office_supplies"}))
    body = client_of(stack).get("/receipts/SYN-1/shadow").json()
    assert body["lines"][0]["agrees_all"] is True
    assert body["summary"] == {"lines": 1, "comparable": 1, "agree_category": 1, "agree_all": 1}


def test_a_line_the_shadow_could_not_classify_is_shown_but_not_comparable(stack: Stack) -> None:
    shadow = BillingClassifier(
        {DESCRIPTION: "office_supplies"}, unclassified_reasons={DESCRIPTION: "budget_refused"}
    )
    run_with_shadow(stack, shadow)
    body = client_of(stack).get("/receipts/SYN-1/shadow").json()
    assert body["lines"][0]["shadow"]["status"] == "unclassified"
    assert body["lines"][0]["shadow"]["unclassified_reason"] == "budget_refused"
    assert body["lines"][0]["shadow"]["category"] is None
    assert body["summary"] == {"lines": 1, "comparable": 0, "agree_category": 0, "agree_all": 0}


def test_an_unknown_receipt_is_404_not_found(stack: Stack) -> None:
    response = client_of(stack).get("/receipts/NOPE/shadow")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_a_receipt_without_shadow_rows_is_404_no_shadow(stack: Stack) -> None:
    stack.service.submit(receipt_json())
    stack.worker(notebook_classifier()).run_once()  # shadow off
    response = client_of(stack).get("/receipts/SYN-1/shadow")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "no_shadow"
    assert set(response.json()["error"]) == {"code", "message", "details"}


def test_a_receipt_whose_shadow_work_is_still_pending_is_404_no_shadow(stack: Stack) -> None:
    stack.service.submit(receipt_json())
    worker = stack.worker(
        notebook_classifier(),
        shadow=BillingClassifier({DESCRIPTION: "tobacco"}),
        shadow_name="jev-hybrid",
    )
    worker.process_next()  # classify only: evaluate and shadow are queued
    assert client_of(stack).get("/receipts/SYN-1/shadow").json()["error"]["code"] == "no_shadow"


def test_the_shadow_describes_the_current_revision_only(stack: Stack) -> None:
    run_with_shadow(stack, BillingClassifier({DESCRIPTION: "tobacco"}))
    stack.service.submit(receipt_json(amount="99.00"))  # revision 2, not yet processed
    response = client_of(stack).get("/receipts/SYN-1/shadow")
    assert response.status_code == 404 and response.json()["error"]["code"] == "no_shadow"
    stack.worker(
        notebook_classifier(),
        shadow=BillingClassifier({DESCRIPTION: "tobacco"}),
        shadow_name="jev-hybrid",
    ).run_once()
    assert client_of(stack).get("/receipts/SYN-1/shadow").json()["revision"] == 2


def test_the_endpoint_changes_nothing_it_only_reads(stack: Stack) -> None:
    run_with_shadow(stack, BillingClassifier({DESCRIPTION: "tobacco"}))
    client = client_of(stack)
    before = client.get("/receipts/SYN-1").json()
    client.get("/receipts/SYN-1/shadow")
    assert client.get("/receipts/SYN-1").json() == before
    assert stack.service.open_work() == 0


def test_the_schemas_and_the_path_are_in_the_openapi_document() -> None:
    document: dict[str, Any] = openapi_document()
    assert "/receipts/{receipt_id}/shadow" in document["paths"]
    schemas = document["components"]["schemas"]
    assert {"ShadowLine", "ShadowView"} <= set(schemas)
    operation = document["paths"]["/receipts/{receipt_id}/shadow"]["get"]
    ok = operation["responses"]["200"]["content"]["application/json"]["schema"]
    assert ok == {"$ref": "#/components/schemas/ShadowView"}
    assert set(schemas["ShadowView"]["properties"]) == {
        "receipt_id",
        "revision",
        "primary",
        "shadow",
        "lines",
        "summary",
        "created_at",
    }
    json.dumps(document)  # serialisable
