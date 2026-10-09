"""Byte-identical output, order independence, tracer independence, and no answers in traces
(T070, SC-003, FR-027, FR-028, constitution II)."""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any

from eval.answers import load_answers
from expense_validator.adapters.classification_cache import ClassificationCache
from expense_validator.adapters.config_files import load_settings
from expense_validator.adapters.openrouter.classifier import OpenRouterClassifier
from expense_validator.adapters.receipts_file import load_receipts
from expense_validator.adapters.results_files import write_results
from expense_validator.adapters.tracing import NoopTracer
from expense_validator.app.pipeline import run_pipeline
from expense_validator.paths import CLASSIFICATIONS_FILE
from expense_validator.ports.tracer import Tracer
from tests.fakes import RecordingTracer


def _run(tmp: Path, name: str, tracer: Tracer, shuffle: bool = False) -> bytes:
    receipts = load_receipts()
    if shuffle:
        random.Random(11).shuffle(receipts)
    clf = OpenRouterClassifier(ClassificationCache(CLASSIFICATIONS_FILE), tracer, offline=True)
    results = run_pipeline(receipts, clf, tracer, load_settings(), run_label="determinism")
    path = tmp / f"{name}.jsonl"
    write_results(path, results)
    return path.read_bytes()


def test_twice_shuffled_and_traced_runs_are_byte_identical(tmp_path: Path) -> None:
    first = _run(tmp_path, "a", NoopTracer())
    assert first == _run(tmp_path, "b", NoopTracer())
    assert first == _run(tmp_path, "c", NoopTracer(), shuffle=True)
    assert first == _run(tmp_path, "d", RecordingTracer())


def _walk(value: Any) -> list[Any]:
    out = [value]
    if isinstance(value, dict):
        out += [k for k in value] + [x for v in value.values() for x in _walk(v)]
    elif isinstance(value, list | tuple):
        out += [x for v in value for x in _walk(v)]
    return out


def test_no_answer_data_reaches_a_trace(tmp_path: Path) -> None:
    tracer = RecordingTracer()
    _run(tmp_path, "traced", tracer)
    captured = [
        x
        for obs in tracer.observations
        for x in _walk(json.loads(json.dumps([obs.fields, obs.updates], default=str)))
    ]
    strings = {x for x in captured if isinstance(x, str)}
    assert not {"labels", "notes", "expected_exceptions"} & strings
    answer_text = set()
    for answer in load_answers().values():
        if answer.notes:
            answer_text.add(answer.notes)
        answer_text |= {e["reason"] for e in answer.exceptions if e.get("reason")}
        answer_text |= {s["reason"] for s in answer.signals if s.get("reason")}
    blob = "\n".join(sorted(strings))
    assert not [t for t in answer_text if t in blob]
