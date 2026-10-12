"""A browser front on another origin can call the API (CORS), and only the listed origins."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from expense_validator.app.api import DEFAULT_CORS_ORIGINS, create_app
from expense_validator.app.composition import cors_origins
from tests.support import build_stack

VITE = "http://localhost:5173"


@pytest.fixture
def stack_service(tmp_path: Path):  # type: ignore[no-untyped-def]
    return build_stack(tmp_path).service


def preflight(
    client: TestClient,
    origin: str,
    method: str = "POST",
    headers: str = "content-type,idempotency-key",
):  # type: ignore[no-untyped-def]
    return client.options(
        "/receipts",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": method,
            "Access-Control-Request-Headers": headers,
        },
    )


def test_the_vite_dev_server_is_allowed_by_default(stack_service) -> None:  # type: ignore[no-untyped-def]
    assert VITE in DEFAULT_CORS_ORIGINS
    response = preflight(TestClient(create_app(stack_service)), VITE)
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == VITE
    allowed = response.headers["access-control-allow-headers"].lower()
    assert "idempotency-key" in allowed and "content-type" in allowed
    assert "POST" in response.headers["access-control-allow-methods"]


def test_a_simple_request_from_an_allowed_origin_carries_the_header(stack_service) -> None:  # type: ignore[no-untyped-def]
    client = TestClient(create_app(stack_service))
    response = client.get("/health", headers={"Origin": VITE})
    assert response.headers["access-control-allow-origin"] == VITE


def test_an_origin_that_is_not_listed_gets_no_permission(stack_service) -> None:  # type: ignore[no-untyped-def]
    client = TestClient(create_app(stack_service))
    response = client.get("/health", headers={"Origin": "https://evil.example"})
    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers
    assert "access-control-allow-origin" not in preflight(client, "https://evil.example").headers


def test_the_list_of_origins_is_configurable(stack_service) -> None:  # type: ignore[no-untyped-def]
    client = TestClient(create_app(stack_service, cors_origins=["https://app.example.com"]))
    assert preflight(client, "https://app.example.com").headers["access-control-allow-origin"] == (
        "https://app.example.com"
    )
    assert "access-control-allow-origin" not in preflight(client, VITE).headers


def test_error_responses_also_carry_the_header_so_the_front_can_read_them(stack_service) -> None:  # type: ignore[no-untyped-def]
    client = TestClient(create_app(stack_service))
    response = client.get("/receipts/NOPE", headers={"Origin": VITE})
    assert response.status_code == 404
    assert response.headers["access-control-allow-origin"] == VITE


def test_origins_come_from_the_flag_then_the_environment_then_the_defaults() -> None:
    assert cors_origins(["https://a.example"], {"EPV_CORS_ORIGINS": "https://b.example"}) == [
        "https://a.example"
    ]
    assert cors_origins(None, {"EPV_CORS_ORIGINS": "https://b.example, https://c.example"}) == [
        "https://b.example",
        "https://c.example",
    ]
    assert cors_origins(None, {}) == list(DEFAULT_CORS_ORIGINS)
