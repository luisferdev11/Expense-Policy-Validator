"""Uploading the 32 receipts gives byte-identical results to `epv run` (iteration 2.1 parity)."""

from __future__ import annotations

import shutil
from pathlib import Path

from expense_validator.adapters.classification_cache import ClassificationCache
from expense_validator.adapters.config_files import load_pipeline_config
from expense_validator.adapters.openrouter.classifier import OpenRouterClassifier
from expense_validator.adapters.openrouter.models import PINS
from expense_validator.adapters.receipts_file import load_receipts
from expense_validator.adapters.tracing import NoopTracer
from expense_validator.app.intake import parse_upload, run_upload
from expense_validator.paths import CLASSIFICATIONS_FILE, RESULTS_FILE


def test_uploading_the_dataset_reproduces_the_committed_results(tmp_path: Path) -> None:
    cache = tmp_path / "cache.jsonl"
    shutil.copy(CLASSIFICATIONS_FILE, cache)
    upload = "".join(r.model_dump_json() + "\n" for r in load_receipts())
    parsed = parse_upload(upload)
    assert not parsed.errors and len(parsed.receipts) == 32
    classifier = OpenRouterClassifier(
        ClassificationCache(cache),
        NoopTracer(),
        offline=True,
        pin=PINS[load_pipeline_config().classifier_model],
    )
    run = run_upload(parsed.receipts, classifier, NoopTracer(), out_dir=tmp_path)
    assert classifier.calls_made == 0
    assert run.path.read_bytes() == RESULTS_FILE.read_bytes()
