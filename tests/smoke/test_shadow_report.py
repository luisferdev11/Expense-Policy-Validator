"""`epv shadow report` on a temporary store: the agreement figures, with their N, and the effect on
the disposition, computed from the store alone with no model call (spec 007, FR-016)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from expense_validator.adapters.config_files import load_settings
from expense_validator.app import cli
from expense_validator.app.shadow_report import build_shadow_report, render, to_dict
from expense_validator.domain.events import LineCategoryCorrected
from tests.fakes import BillingClassifier
from tests.support import Stack, build_stack, receipt_json

COUNT = 8
IDS = [f"SYN-{n}" for n in range(COUNT)]
DESCRIPTIONS = {f"Item {n}": "office_supplies" for n in range(COUNT)}
# the shadow disagrees on two lines (a restricted category) and agrees on the other six
DISAGREE = {"Item 1": "tobacco", "Item 4": "alcohol"}
SHADOW = {**DESCRIPTIONS, **DISAGREE}


def populated(tmp_path: Path, corrections: bool = True) -> Stack:
    stack = build_stack(tmp_path)
    for n, rid in enumerate(IDS):
        stack.service.submit(receipt_json(rid, "10.00", f"Item {n}", employee_id=f"E-{n}"))
    stack.worker(
        BillingClassifier(DESCRIPTIONS),
        shadow=BillingClassifier(SHADOW),
        shadow_name="jev-hybrid",
    ).run_once()
    if corrections:
        now = datetime(2026, 10, 12, 18, 0, tzinfo=UTC)
        with stack.store.transaction() as tx:
            # a reviewer sides with the primary on SYN-1 and with neither on SYN-4
            event = LineCategoryCorrected(
                line_id="SYN-1-L1",
                from_category="office_supplies",
                to_category="office_supplies",
                based_on_version=1,
                agreement=0,
            )
            tx.append_event("SYN-1", 1, event, "alice", now)
            tx.append_event(
                "SYN-4",
                1,
                event.model_copy(update={"line_id": "SYN-4-L1", "to_category": "gift"}),
                "alice",
                now,
            )
    return stack


def test_the_report_counts_agreement_with_its_n(tmp_path: Path) -> None:
    stack = populated(tmp_path)
    (report,) = build_shadow_report(stack.store, load_settings())
    assert report.classifier == "jev-hybrid"
    a = report.agreement
    assert (a.receipts, a.lines, a.comparable) == (COUNT, COUNT, COUNT)
    assert (a.category.k, a.category.n) == (6, 8)
    assert a.category.rate == 0.75 and a.category.interval is not None
    assert (a.restricted.k, a.restricted.n) == (6, 8)  # tobacco and alcohol are restricted
    assert (a.subtype.k, a.recipient_kind.k, a.all_fields.k) == (8, 8, 6)
    assert [(c.primary, c.shadow, c.count) for c in a.confusion] == [
        ("office_supplies", "alcohol", 1),
        ("office_supplies", "tobacco", 1),
    ]
    assert a.shadow_unclassified == {}


def test_the_report_scores_each_classifier_against_the_reviewer(tmp_path: Path) -> None:
    stack = populated(tmp_path)
    (report,) = build_shadow_report(stack.store, load_settings())
    c = report.agreement.corrections
    assert (c.corrected_lines, c.n) == (2, 2)
    assert (c.primary.k, c.primary.n) == (1, 2)  # right on SYN-1, wrong on SYN-4
    assert (c.shadow.k, c.shadow.n) == (0, 2)  # wrong on both


def test_the_disposition_impact_reruns_the_unchanged_decision_code(tmp_path: Path) -> None:
    stack = populated(tmp_path)
    (report,) = build_shadow_report(stack.store, load_settings())
    impact = report.disposition
    assert impact.receipts.n == COUNT
    assert 0 < impact.receipts.k <= len(DISAGREE)  # only the receipts the shadow disagrees on
    assert sum(impact.changes.values()) == impact.receipts.k
    assert all("->" in change for change in impact.changes)
    # it changed nothing in the store
    assert stack.service.get_receipt("SYN-1").record.disposition is not None
    assert stack.service.open_work() == 0


def test_without_shadow_rows_there_is_no_report(tmp_path: Path) -> None:
    stack = build_stack(tmp_path)
    assert build_shadow_report(stack.store, load_settings()) == []


def test_the_command_prints_the_report_and_makes_no_model_call(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    stack = populated(tmp_path)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)  # there is no key, and none is needed
    assert cli.main(["shadow", "report", "--db", str(stack.store.path)]) == 0
    out = capsys.readouterr().out
    assert "jev-hybrid" in out
    assert "category agreement: 6/8" in out
    assert "75.0 %" in out and "95 % CI" in out
    assert "reviewer corrections: 2 corrected lines" in out
    assert "disposition would differ" in out
    assert "office_supplies -> tobacco" in out


def test_the_json_output_has_the_same_content(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    stack = populated(tmp_path)
    assert cli.main(["shadow", "report", "--db", str(stack.store.path), "--json"]) == 0
    document = json.loads(capsys.readouterr().out)
    (entry,) = document["reports"]
    assert entry["classifier"] == "jev-hybrid"
    assert entry["agreement"]["category"] == {
        "k": 6,
        "n": 8,
        "rate": 0.75,
        "interval": entry["agreement"]["category"]["interval"],
    }
    assert len(entry["agreement"]["category"]["interval"]) == 2
    assert entry["agreement"]["corrections"]["primary"]["k"] == 1
    assert entry["disposition"]["receipts"]["n"] == COUNT
    (report,) = build_shadow_report(stack.store, load_settings())
    assert entry == to_dict(report)
    assert "jev-hybrid" in render([report])


def test_an_empty_store_says_so_and_exits_cleanly(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(["shadow", "report", "--db", str(tmp_path / "e.sqlite3")]) == 0
    assert "no shadow answers" in capsys.readouterr().out
    assert cli.main(["shadow", "report", "--db", str(tmp_path / "e.sqlite3"), "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == {"reports": []}


def test_a_stale_revision_does_not_count(tmp_path: Path) -> None:
    stack = populated(tmp_path, corrections=False)
    stack.service.submit(receipt_json("SYN-0", "99.00", "Item 0", employee_id="E-0"))  # revision 2
    (report,) = build_shadow_report(stack.store, load_settings())
    assert report.agreement.receipts == COUNT - 1  # SYN-0's shadow rows are for revision 1
