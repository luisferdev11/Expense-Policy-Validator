"""Run the engine on synthetic receipts and read the result compactly."""

from __future__ import annotations

from typing import Any

from expense_validator.models import Classification, ClassifiedReceipt, EngineFindings
from tests.engine_cases.helpers import run
from tests.factories import classified, item, receipt


def engine(
    items: list[dict[str, Any]],
    categories: list[str | Classification],
    batch: list[ClassifiedReceipt] | None = None,
    **receipt_fields: Any,
) -> EngineFindings:
    r = classified(receipt(items, **receipt_fields), *categories)
    return run(r, batch=[r, *(batch or [])])


def one(categories: list[str | Classification], **fields: Any) -> EngineFindings:
    """One synthetic line per category, $10 each unless overridden by `amounts`."""
    amounts = fields.pop("amounts", None) or ["10.00"] * len(categories)
    items = [item(i + 1, amount=a) for i, a in enumerate(amounts)]
    return engine(items, categories, **fields)


def exc(findings: EngineFindings, rule_id: str) -> Any:
    found = [e for e in findings.exceptions if e.rule_id == rule_id]
    return found[0] if found else None


def ids(findings: EngineFindings) -> set[str]:
    return {e.rule_id for e in findings.exceptions}


def signals(findings: EngineFindings) -> set[str]:
    return {s.rule_id for s in findings.review_signals}
