"""Configuration files: build the engine's Settings and compute the rules version.

Reads docs/decisions/policy_decisions.yaml (decisions A1-A9) and the versioned tables in
config/. The domain receives the resulting `Settings` value and never reads a file (ADR 0003).
"""

from __future__ import annotations

import csv
import hashlib
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import yaml

from expense_validator.adapters.openrouter.models import CLASSIFIER_NAMES
from expense_validator.domain.engine.settings import Settings
from expense_validator.paths import CONFIG_DIR, DECISIONS_FILE, POLICY_DIR, REPO_ROOT

ENGINE_DIR = REPO_ROOT / "src" / "expense_validator" / "domain" / "engine"


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8") as fh:
        lines = [line for line in fh if line.strip() and not line.startswith("#")]
    return list(csv.DictReader(lines))


def _config(decisions: list[dict[str, Any]]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for decision in decisions:
        merged.update(decision.get("config") or {})
    return merged


def load_settings(decisions_file: Path = DECISIONS_FILE, config_dir: Path = CONFIG_DIR) -> Settings:
    with decisions_file.open(encoding="utf-8") as fh:
        decisions: list[dict[str, Any]] = yaml.safe_load(fh)["decisions"]
    config = _config(decisions)
    return Settings(
        fx_date_basis=str(config["fx.date_basis"]),
        fx_rate_kind=str(config["fx.rate_kind"]),
        fx_missing_rate_disposition=str(config["fx.missing_rate_disposition"]),
        exc03_threshold=Decimal(str(config["exc03.threshold"])),
        exc03_threshold_status=str(config.get("exc03.threshold_status", "provisional")),
        reference_prefixes={str(k): str(v) for k, v in config["reference_prefixes"].items()},
        decision_ids=tuple(str(d["id"]) for d in decisions),
        home_currency={
            row["country"]: row["currency"]
            for row in _rows(config_dir / "iso4217_country_currency.csv")
        },
        eur_to_usd={
            date.fromisoformat(row["date"]): Decimal(row["eur_to_usd"])
            for row in _rows(config_dir / "eur_rates.csv")
        },
    )


@dataclass(frozen=True)
class PipelineConfig:
    """The iteration 2 winners (ADR 0005): which pin classifies, and how its answers are read."""

    classifier_model: str
    confidence_source: str
    translate: bool
    null_subtype_as_none: bool
    version: str


PIPELINE_FILE = CONFIG_DIR / "pipeline.yaml"


def load_pipeline_config(path: Path = PIPELINE_FILE) -> PipelineConfig:
    raw = path.read_bytes()
    data: dict[str, Any] = yaml.safe_load(raw)
    classifier_model = str(data["classifier_model"])
    if classifier_model not in CLASSIFIER_NAMES:
        raise ValueError(
            f"unknown classifier_model {classifier_model!r} in {path.name}; "
            f"accepted: {', '.join(CLASSIFIER_NAMES)}"
        )
    return PipelineConfig(
        classifier_model=classifier_model,
        confidence_source=str(data["confidence_source"]),
        translate=bool(data["translate"]),
        null_subtype_as_none=bool(data["null_subtype_as_none"]),
        version=hashlib.sha256(raw).hexdigest()[:12],
    )


def rules_version() -> str:
    """12 hex chars of a SHA-256 over the engine source, the decisions and the policies."""
    paths = [
        *sorted(ENGINE_DIR.rglob("*.py")),
        DECISIONS_FILE,
        *sorted(POLICY_DIR.glob("*.md")),
    ]
    digest = hashlib.sha256()
    for path in paths:
        digest.update(path.name.encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()[:12]
