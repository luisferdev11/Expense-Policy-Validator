"""Engine settings, read from docs/decisions/policy_decisions.yaml and the config tables.

The decisions file is the single source for configurable policy choices (ADR 0001, ADR 0002).
This module reads files once at load time; the engine receives the resulting `Settings` value.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import yaml

from expense_validator.paths import CONFIG_DIR, DECISIONS_FILE


@dataclass(frozen=True)
class Settings:
    fx_date_basis: str
    fx_rate_kind: str
    fx_missing_rate_disposition: str
    exc03_threshold: Decimal
    reference_prefixes: dict[str, str]
    decision_ids: tuple[str, ...]
    home_currency: dict[str, str] = field(default_factory=dict)
    eur_to_usd: dict[date, Decimal] = field(default_factory=dict)


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
