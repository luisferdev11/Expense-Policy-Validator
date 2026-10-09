"""The engine's settings: a plain value built by an adapter (adapters/config_files.py).

The decisions file `docs/decisions/policy_decisions.yaml` is the single source for configurable
policy choices (ADR 0001); the engine never reads it itself (ADR 0003).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal


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
