"""Intake of uploaded receipts (iteration 2.1): parse, validate, run the pipeline on the batch.

An upload is one receipt (a JSON object), a JSON array, or JSONL. Each row goes through
`parse_receipt_line`, so answer keys are stripped exactly as for the dataset. A bad row is
reported with its row number and the others still run. The cross-receipt context is the
uploaded batch. The run id is a hash of the receipts, so the same upload gives the same id, the
same output file and, through the classification cache, no new billed calls.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import ValidationError

from expense_validator.adapters.classification_cache import ClassificationCache
from expense_validator.adapters.config_files import load_pipeline_config, load_settings
from expense_validator.adapters.openrouter.classifier import OpenRouterClassifier
from expense_validator.adapters.openrouter.models import PINS
from expense_validator.adapters.receipts_file import parse_receipt_line
from expense_validator.adapters.results_files import write_results
from expense_validator.app.pipeline import run_pipeline
from expense_validator.domain.models import ReceiptInput, ReceiptResult
from expense_validator.paths import CLASSIFICATIONS_FILE, REPO_ROOT
from expense_validator.ports.classifier import ItemClassifier
from expense_validator.ports.tracer import Tracer

UPLOADS_DIR = REPO_ROOT / ".cache" / "uploads"
UPLOAD_CACHE = REPO_ROOT / ".cache" / "upload_classifications.jsonl"


@dataclass(frozen=True)
class ParsedUpload:
    receipts: list[ReceiptInput]
    errors: list[tuple[int, str]] = field(default_factory=list)


@dataclass(frozen=True)
class UploadRun:
    run_id: str
    results: list[ReceiptResult]
    path: Path


def _rows(text: str) -> list[str]:
    """Split an upload into one JSON text per receipt."""
    stripped = text.strip()
    if stripped.startswith("["):
        try:
            return [json.dumps(row) for row in json.loads(stripped)]
        except json.JSONDecodeError:
            pass
    if stripped.startswith("{") and "\n" in stripped:
        try:
            whole = json.loads(stripped)
        except json.JSONDecodeError:
            whole = None
        if isinstance(whole, dict):
            return [json.dumps(whole)]
    return [line for line in text.splitlines() if line.strip()]


def parse_upload(text: str) -> ParsedUpload:
    receipts: list[ReceiptInput] = []
    errors: list[tuple[int, str]] = []
    seen: set[str] = set()
    for row, raw in enumerate(_rows(text), start=1):
        try:
            parsed = parse_receipt_line(raw)
        except json.JSONDecodeError as exc:
            errors.append((row, f"not valid JSON: {exc.msg}"))
            continue
        except ValidationError as exc:
            fields = sorted({".".join(str(p) for p in e["loc"]) for e in exc.errors()})
            errors.append((row, f"not a valid receipt: {', '.join(fields[:5])}"))
            continue
        if parsed.receipt_id in seen:
            errors.append((row, f"duplicate receipt_id {parsed.receipt_id} in this upload"))
            continue
        seen.add(parsed.receipt_id)
        receipts.append(parsed)
    return ParsedUpload(receipts, errors)


def run_id(receipts: list[ReceiptInput]) -> str:
    canonical = "\n".join(r.model_dump_json() for r in sorted(receipts, key=lambda r: r.receipt_id))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:12]


def default_classifier(tracer: Tracer, cache_path: Path = UPLOAD_CACHE) -> OpenRouterClassifier:
    """The configured classifier on a gitignored cache, seeded from the committed one, so
    uploads never change committed outputs and known lines cost nothing."""
    if not cache_path.exists() and CLASSIFICATIONS_FILE.exists():
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(CLASSIFICATIONS_FILE, cache_path)
    config = load_pipeline_config()
    return OpenRouterClassifier(
        ClassificationCache(cache_path),
        tracer,
        pin=PINS[config.classifier_model],
        null_subtype_as_none=config.null_subtype_as_none,
    )


def run_upload(
    receipts: list[ReceiptInput],
    classifier: ItemClassifier,
    tracer: Tracer,
    out_dir: Path = UPLOADS_DIR,
) -> UploadRun:
    rid = run_id(receipts)
    results = run_pipeline(
        receipts, classifier, tracer, load_settings(), f"upload-{rid}", load_pipeline_config()
    )
    cache = getattr(classifier, "cache", None)
    if isinstance(cache, ClassificationCache) and cache.dirty:
        cache.save()
    path = out_dir / f"{rid}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    write_results(path, results)
    return UploadRun(rid, results, path)
