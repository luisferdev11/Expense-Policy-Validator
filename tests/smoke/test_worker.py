"""`epv worker --once` drains the queue of a database file (smoke test, offline)."""

from __future__ import annotations

from pathlib import Path

import pytest

from expense_validator.adapters.sqlite_cache import SqliteClassificationCache
from expense_validator.adapters.sqlite_store import SqliteStore, utc_now
from expense_validator.app import cli
from expense_validator.app.service import ReceiptService
from tests.support import receipt_json


def test_worker_once_processes_what_was_submitted(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    db = tmp_path / "epv.sqlite3"
    service = ReceiptService(SqliteStore(db), utc_now)
    service.submit(receipt_json())

    argv = ["worker", "--once", "--offline", "--no-trace", "--db", str(db)]
    assert cli.main(argv) == 0

    assert "processed 2 work items" in capsys.readouterr().err
    view = service.get_receipt("SYN-1")
    # offline and not in the committed cache: the line is unclassified, so EXC-03 asks for review
    assert view.record.state == "in_review" and view.record.disposition == "review"
    # the answer table was seeded from the committed file, which is left untouched
    assert len(SqliteClassificationCache(db, utc_now)) == 78


def test_an_empty_queue_is_a_clean_run(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    argv = ["worker", "--once", "--offline", "--no-trace", "--db", str(tmp_path / "e.sqlite3")]
    assert cli.main(argv) == 0
    assert "processed 0 work items" in capsys.readouterr().err
