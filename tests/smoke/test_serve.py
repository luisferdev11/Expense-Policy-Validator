"""`epv serve` wires the API over a database file (smoke test, no socket is opened)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from expense_validator.app import cli
from expense_validator.app.composition import db_path


def test_the_database_path_prefers_the_flag_then_the_environment_then_the_default() -> None:
    assert db_path("a.sqlite3", {"EPV_DB": "b.sqlite3"}) == Path("a.sqlite3")
    assert db_path(None, {"EPV_DB": "b.sqlite3"}) == Path("b.sqlite3")
    assert db_path(None, {}).name == "epv.sqlite3" and db_path(None, {}).parent.name == "var"


def test_serve_builds_the_app_and_hands_it_to_uvicorn(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import uvicorn

    seen: dict[str, Any] = {}
    monkeypatch.setattr(uvicorn, "run", lambda app, **kwargs: seen.update(app=app, **kwargs))
    code = cli.main(["serve", "--port", "8123", "--db", str(tmp_path / "epv.sqlite3")])
    assert code == 0
    assert isinstance(seen["app"], FastAPI)
    assert (seen["host"], seen["port"]) == ("127.0.0.1", 8123)
    assert TestClient(seen["app"]).get("/health").json()["status"] == "ok"
    assert (tmp_path / "epv.sqlite3").exists()
