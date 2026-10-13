"""The committed OpenAPI document is the API's contract; this keeps it from drifting."""

from __future__ import annotations

import json

import pytest

from expense_validator.app import cli
from expense_validator.app.composition import openapi_document
from expense_validator.paths import REPO_ROOT

COMMITTED = REPO_ROOT / "docs" / "api" / "openapi.json"
EXPECTED_PATHS = {
    "/health",
    "/receipts",
    "/receipts/{receipt_id}",
    "/receipts/{receipt_id}/events",
    "/receipts/{receipt_id}/shadow",
    "/receipts/{receipt_id}/revisions/{revision}",
    "/receipts/{receipt_id}/retry",
    "/receipts/{receipt_id}/actions/{action}",
    "/batches",
    "/batches/{batch_id}",
}


def test_the_document_describes_every_endpoint() -> None:
    assert set(openapi_document()["paths"]) == EXPECTED_PATHS


def test_the_committed_document_is_up_to_date() -> None:
    fresh = json.dumps(openapi_document(), indent=2, sort_keys=True) + "\n"
    assert COMMITTED.read_text(encoding="utf-8") == fresh, (
        "docs/api/openapi.json is stale: run `uv run epv openapi > docs/api/openapi.json`"
    )


def test_the_command_prints_the_document(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["openapi"]) == 0
    assert json.loads(capsys.readouterr().out) == openapi_document()
