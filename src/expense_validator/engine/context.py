"""Cross-receipt context: aggregates that span receipts, built once per batch (FR-021).

Thin-path version: an empty context. MEAL-01, REG-02, REG-03 and HEALTH-01 fill it in Phase 4.
"""

from __future__ import annotations

from collections.abc import Sequence

from expense_validator.engine.settings import Settings
from expense_validator.models import ClassifiedReceipt, CrossReceiptContext


def build_context(batch: Sequence[ClassifiedReceipt], settings: Settings) -> CrossReceiptContext:
    return CrossReceiptContext()
