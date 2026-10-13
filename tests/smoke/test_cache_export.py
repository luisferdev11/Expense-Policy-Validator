"""`epv cache export` writes the answer table as the committed file, byte for byte (SC-003)."""

from __future__ import annotations

from pathlib import Path

import pytest

from expense_validator.app import cli
from expense_validator.paths import CLASSIFICATIONS_FILE


def test_a_fresh_database_exports_the_committed_file_exactly(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    db = tmp_path / "fresh.sqlite3"
    assert cli.main(["cache", "export", "--db", str(db)]) == 0
    captured = capsys.readouterr()
    assert captured.out.encode("utf-8") == CLASSIFICATIONS_FILE.read_bytes()
    assert "78 rows" in captured.err


def test_the_export_can_go_to_a_file(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    out = tmp_path / "exported.jsonl"
    argv = ["cache", "export", "--db", str(tmp_path / "e.sqlite3"), "--out", str(out)]
    assert cli.main(argv) == 0
    assert out.read_bytes() == CLASSIFICATIONS_FILE.read_bytes()
    assert capsys.readouterr().out == ""
