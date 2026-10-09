"""Shared helpers for engine-case tests: real receipts through the loader, hand classifications.

Hand classifications are written from each line's description only, never from answer fields.
"""

from __future__ import annotations

from functools import cache

from expense_validator.engine.context import build_context
from expense_validator.engine.evaluate import evaluate
from expense_validator.engine.registry import REGISTRY
from expense_validator.engine.settings import Settings, load_settings
from expense_validator.loader import load_receipts
from expense_validator.models import (
    Classification,
    ClassifiedReceipt,
    CrossReceiptContext,
    EngineFindings,
    ReceiptInput,
    RuleSet,
)
from tests.factories import classified

ALL_RULES = RuleSet(rule_ids=tuple(sorted(REGISTRY)))


@cache
def settings() -> Settings:
    return load_settings()


@cache
def _receipts() -> dict[str, ReceiptInput]:
    return {r.receipt_id: r for r in load_receipts()}


def real(receipt_id: str) -> ReceiptInput:
    return _receipts()[receipt_id]


def hand(receipt_id: str, *categories: str | Classification) -> ClassifiedReceipt:
    return classified(real(receipt_id), *categories)


def run(
    receipt: ClassifiedReceipt,
    context: CrossReceiptContext | None = None,
    batch: list[ClassifiedReceipt] | None = None,
) -> EngineFindings:
    if context is None:
        context = build_context(batch or [receipt], settings())
    return evaluate(receipt, context, ALL_RULES, settings())


def rule_ids(findings: EngineFindings) -> set[str]:
    return {e.rule_id for e in findings.exceptions}


def signal_ids(findings: EngineFindings) -> set[str]:
    return {s.rule_id for s in findings.review_signals}
