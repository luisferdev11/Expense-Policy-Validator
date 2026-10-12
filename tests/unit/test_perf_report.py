"""The load-test report is built from raw files with no load run (spec 006, research R15)."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from perf.report import RunInfo, render

FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "perf"
INFO = RunInfo(
    commit="abc1234",
    date="2026-10-12",
    python="3.12.14",
    sqlite="3.45.1",
    cpu="Test CPU",
    cores=12,
    command="uv run locust -f perf/locustfile.py --headless --profile nominal",
)


@pytest.fixture
def raw(tmp_path: Path) -> Path:
    shutil.copytree(FIXTURE, tmp_path / "raw")
    return tmp_path / "raw"


def test_the_report_names_the_commit_the_machine_and_the_command(raw: Path) -> None:
    text = render("nominal", raw, INFO)
    for expected in ("abc1234", "3.12.14", "3.45.1", "Test CPU", "12 cores", "--profile nominal"):
        assert expected in text


def test_the_profile_row_comes_from_the_profiles_module(raw: Path) -> None:
    text = render("nominal", raw, INFO)
    assert "| nominal | 10 | 1.2 | 300 s |" in text


def test_every_endpoint_has_its_n_percentiles_and_failures(raw: Path) -> None:
    text = render("nominal", raw, INFO)
    assert "| GET /receipts (list) | 1080 | 0 | 22 | 450 | 600 | 3.60 |" in text
    assert "| POST /batches (100 rows) | 4 | 2 | 2400 | 2800 | 2800 | 0.01 |" in text
    assert "| all requests | 3250 | 2 | 12 | 320 | 520 | 10.83 |" in text


def test_the_failures_are_listed_with_their_error(raw: Path) -> None:
    text = render("nominal", raw, INFO)
    assert "503 Server Error" in text and "2 times" in text


def test_the_queue_section_has_the_backlog_the_drain_and_the_receipts_evaluated(raw: Path) -> None:
    text = render("nominal", raw, INFO)
    assert "Peak backlog: 17 items (9 samples, every 0.5 s)" in text
    assert "Drain time: 38.5 s" in text
    assert "Receipts evaluated: 1500 (1200 auto_approved, 300 in_review, 0 compliance)" in text


def test_the_thresholds_section_names_each_miss_and_each_met(raw: Path) -> None:
    text = render("nominal", raw, INFO)
    section = text.split("## Thresholds", 1)[1]
    assert "GET /receipts (list): p95 450 ms is above 300 ms (miss)" in section
    assert "POST /receipts: p95 400 ms is within 500 ms (met)" in section
    assert "GET /receipts/[id]: p95 120 ms is within 300 ms (met)" in section
    assert "the queue drained 38.5 s after the load stopped (met)" in section


def test_a_run_that_did_not_drain_says_so(raw: Path) -> None:
    (raw / "drain.json").write_text(
        '{"drain_seconds": null, "timeout_s": 600, "remaining": 120, '
        '"evaluated": {"total": 900, "auto_approved": 900, "in_review": 0, "compliance": 0}}',
        encoding="utf-8",
    )
    text = render("nominal", raw, INFO)
    assert "did not drain within 600 s: 120 items left" in text
    assert "the queue did not drain (miss)" in text


def test_a_profile_other_than_nominal_reports_without_judging(raw: Path) -> None:
    text = render("peak", raw, INFO)
    section = text.split("## Thresholds", 1)[1]
    assert "reported, not judged" in section
    assert "(miss)" not in section


def test_the_report_reads_the_aws_page_and_names_the_sqlite_limit(raw: Path) -> None:
    text = render("nominal", raw, INFO)
    assert "docs/aws.md" in text and "SQLite" in text


def test_receipts_decided_by_a_reviewer_during_the_run_are_counted_too(raw: Path) -> None:
    (raw / "drain.json").write_text(
        '{"drain_seconds": 12.0, "timeout_s": 600, "remaining": 0, '
        '"evaluated": {"total": 1505, "auto_approved": 1200, "in_review": 295, "compliance": 0, '
        '"decided": 10}}',
        encoding="utf-8",
    )
    text = render("nominal", raw, INFO)
    assert (
        "Receipts evaluated: 1505 (1200 auto_approved, 295 in_review, 0 compliance, "
        "10 approved or rejected)" in text
    )
