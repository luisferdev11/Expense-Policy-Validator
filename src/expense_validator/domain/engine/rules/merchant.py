"""merchant-category-risk.md: MCC-01 to MCC-03, with the risk tier table.

MCC-03 (bars are on-premises) is applied through ON_PREMISES_MCC, used by ALC-01 to ALC-03.
"""

from __future__ import annotations

from expense_validator.domain.engine.base import Hit, Rule, RuleInput

HIGH_RISK_MCC = frozenset({5921, 5993, 7995, 7297, 5944})
MEDIUM_RISK_MCC = frozenset({5813, 5912, 5311, 5411, 5732})
ON_PREMISES_MCC = frozenset({5812, 5813, 7011})


def mcc_01(inp: RuleInput) -> list[Hit]:
    """A high-risk MCC is a high exception on its own, whatever the line items say."""
    if inp.receipt.mcc in HIGH_RISK_MCC:
        return [Hit("MCC-01", computed={"mcc": str(inp.receipt.mcc)})]
    return []


def mcc_02(inp: RuleInput) -> list[Hit]:
    """A medium-risk MCC is always its own review signal, never an exception."""
    if inp.receipt.mcc in MEDIUM_RISK_MCC:
        return [Hit("MCC-02", computed={"mcc": str(inp.receipt.mcc)})]
    return []


RULES: dict[str, Rule] = {"MCC-01": mcc_01, "MCC-02": mcc_02}
