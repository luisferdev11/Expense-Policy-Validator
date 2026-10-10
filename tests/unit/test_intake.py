"""Intake of uploaded receipts (iteration 2.1): parsing, partial success, stable runs."""

from __future__ import annotations

import json
from pathlib import Path

from expense_validator.adapters.keyword_classifier import KeywordClassifier
from expense_validator.adapters.tracing import NoopTracer
from expense_validator.app.intake import parse_upload, run_upload
from tests.factories import item, receipt


def _raw(rid: str, **extra: object) -> dict[str, object]:
    r = receipt([item(1, receipt_id=rid, description="Club sandwich")], receipt_id=rid)
    data: dict[str, object] = json.loads(r.model_dump_json())
    data.update(extra)
    return data


def test_jsonl_array_and_single_object_all_parse() -> None:
    a, b = _raw("UP-1"), _raw("UP-2")
    jsonl = json.dumps(a) + "\n" + json.dumps(b) + "\n"
    assert [r.receipt_id for r in parse_upload(jsonl).receipts] == ["UP-1", "UP-2"]
    assert [r.receipt_id for r in parse_upload(json.dumps([a, b])).receipts] == ["UP-1", "UP-2"]
    single = parse_upload(json.dumps(a, indent=2))
    assert [r.receipt_id for r in single.receipts] == ["UP-1"] and not single.errors


def test_a_bad_row_is_reported_and_the_rest_still_parse() -> None:
    text = json.dumps(_raw("UP-1")) + "\n{not json\n" + json.dumps({"receipt_id": "UP-3"}) + "\n"
    parsed = parse_upload(text)
    assert [r.receipt_id for r in parsed.receipts] == ["UP-1"]
    assert [row for row, _ in parsed.errors] == [2, 3]


def test_answer_keys_are_stripped_and_duplicate_ids_rejected() -> None:
    labelled = _raw("UP-1", labels={"disposition": "pass"}, notes="the answer")
    parsed = parse_upload(json.dumps(labelled) + "\n" + json.dumps(_raw("UP-1")) + "\n")
    assert [r.receipt_id for r in parsed.receipts] == ["UP-1"]
    assert len(parsed.errors) == 1 and "duplicate" in parsed.errors[0][1]


def test_the_same_upload_gives_the_same_run_id_and_results(tmp_path: Path) -> None:
    receipts = parse_upload(json.dumps([_raw("UP-1"), _raw("UP-2")])).receipts
    first = run_upload(receipts, KeywordClassifier(), NoopTracer(), out_dir=tmp_path)
    again = run_upload(
        list(reversed(receipts)), KeywordClassifier(), NoopTracer(), out_dir=tmp_path
    )
    assert first.run_id == again.run_id
    assert [r.receipt_id for r in first.results] == ["UP-1", "UP-2"]
    assert first.path.read_bytes() == again.path.read_bytes()
