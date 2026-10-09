"""Policy retriever: a deterministic trigger map over items, MCC and metadata (research R10).

Each in-scope rule lists the conditions under which it could apply; a rule is selected when any
trigger matches. A test checks that the engine never raises a rule the retriever did not select.
"""

from __future__ import annotations

from collections.abc import Callable

from expense_validator.engine.rules.merchant import MEDIUM_RISK_MCC
from expense_validator.models import ClassifiedReceipt, RuleSet

Trigger = Callable[[ClassifiedReceipt], bool]


def _categories(r: ClassifiedReceipt) -> set[str]:
    return {c.category for c in r.classifications if c.category is not None}


def _has(*categories: str) -> Trigger:
    return lambda r: bool(_categories(r) & set(categories))


TRIGGERS: dict[str, Trigger] = {
    "TECH-02": _has("computer_accessory"),
    "MCC-02": lambda r: r.receipt.mcc in MEDIUM_RISK_MCC,
}


def retrieve(receipt: ClassifiedReceipt) -> RuleSet:
    return RuleSet(rule_ids=tuple(sorted(rid for rid, hit in TRIGGERS.items() if hit(receipt))))
