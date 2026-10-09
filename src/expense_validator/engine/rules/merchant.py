"""merchant-category-risk.md: MCC-01 to MCC-03, with the risk tier table."""

from __future__ import annotations

from expense_validator.engine.base import Hit, Rule, RuleInput

HIGH_RISK_MCC = frozenset({5921, 5993, 7995, 7297, 5944})
MEDIUM_RISK_MCC = frozenset({5813, 5912, 5311, 5411, 5732})


def mcc_02(inp: RuleInput) -> list[Hit]:
    """A medium-risk MCC is always its own review signal, never an exception."""
    if inp.receipt.mcc in MEDIUM_RISK_MCC:
        return [Hit("MCC-02", computed={"mcc": str(inp.receipt.mcc)})]
    return []


RULES: dict[str, Rule] = {"MCC-02": mcc_02}
