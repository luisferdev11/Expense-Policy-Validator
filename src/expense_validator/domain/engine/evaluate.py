"""evaluate(receipt, context, ruleset, settings) -> EngineFindings. Pure and deterministic.

Runs the selected rules, merges hits so each rule appears at most once per receipt (FR-019),
attaches the verbatim evidence from the registry, and computes the EXC-01 disposition.
Explanations and signal reasons are left empty here; the reporter writes them.
"""

from __future__ import annotations

from collections.abc import Iterable

from expense_validator.domain.engine import fx
from expense_validator.domain.engine.base import SEVERITY_ORDER, Hit, Rule, RuleInput
from expense_validator.domain.engine.disposition import disposition
from expense_validator.domain.engine.registry import REGISTRY
from expense_validator.domain.engine.rules import (
    documentation,
    gifts,
    meals,
    merchant,
    non_reimbursable,
    regional,
    technology,
)
from expense_validator.domain.engine.settings import Settings
from expense_validator.domain.engine.uncertainty import exc_03, split_lines
from expense_validator.domain.models import (
    ClassifiedReceipt,
    CrossReceiptContext,
    EngineFindings,
    ExceptionFinding,
    ReviewSignal,
    RuleSet,
    Severity,
)

RULES: dict[str, Rule] = {
    **meals.RULES,
    **technology.RULES,
    **gifts.RULES,
    **non_reimbursable.RULES,
    **merchant.RULES,
    **documentation.RULES,
    **regional.RULES,
    "EXC-03": exc_03,
}


def rule_input(
    classified: ClassifiedReceipt, context: CrossReceiptContext, settings: Settings
) -> RuleInput:
    lines, uncertain = split_lines(classified, settings)
    return RuleInput(classified.receipt, lines, uncertain, context, settings)


def _merge(hits: Iterable[Hit], order: dict[str, int]) -> list[Hit]:
    by_rule: dict[str, list[Hit]] = {}
    for hit in hits:
        by_rule.setdefault(hit.rule_id, []).append(hit)
    merged: list[Hit] = []
    for rule_id in sorted(by_rule):
        group = by_rule[rule_id]
        default = REGISTRY[rule_id].severity

        def rank(h: Hit, default: Severity | None = default) -> int:
            return SEVERITY_ORDER.get(h.severity or default or "low", 0)

        top = max(group, key=rank)
        line_ids = sorted({i for h in group for i in h.line_ids}, key=lambda i: order.get(i, 0))
        computed: dict[str, str] = {}
        for h in group:
            computed.update(h.computed)
        merged.append(
            Hit(
                rule_id,
                tuple(line_ids),
                dict(sorted(computed.items())),
                top.severity,
                top.variant,
                as_signal=any(h.as_signal for h in group),
            )
        )
    return merged


def evaluate(
    classified: ClassifiedReceipt,
    context: CrossReceiptContext,
    ruleset: RuleSet,
    settings: Settings,
) -> EngineFindings:
    fx.check_supported(settings)
    inp = rule_input(classified, context, settings)
    order = {item.line_id: i for i, item in enumerate(classified.receipt.line_items)}
    hits = [hit for rule_id in ruleset.rule_ids if rule_id in RULES for hit in RULES[rule_id](inp)]
    exceptions: list[ExceptionFinding] = []
    signals: list[ReviewSignal] = []
    for hit in _merge(hits, order):
        spec = REGISTRY[hit.rule_id]
        if spec.kind == "exception" and not hit.as_signal:
            severity = hit.severity or spec.severity
            assert severity is not None
            exceptions.append(
                ExceptionFinding(
                    rule_id=spec.rule_id,
                    policy_doc=spec.policy_doc,
                    severity=severity,
                    line_ids=list(hit.line_ids),
                    evidence=spec.evidence_variants.get(hit.variant, spec.evidence),
                    explanation="",
                    decisions=list(spec.decisions),
                    computed=hit.computed,
                )
            )
        elif spec.kind == "review_signal" or hit.as_signal:
            signals.append(
                ReviewSignal(
                    rule_id=spec.rule_id,
                    policy_doc=spec.policy_doc,
                    reason="",
                    line_ids=list(hit.line_ids),
                )
            )
    return EngineFindings(
        exceptions=tuple(exceptions),
        review_signals=tuple(signals),
        disposition=disposition((e.severity for e in exceptions), bool(signals)),
    )
