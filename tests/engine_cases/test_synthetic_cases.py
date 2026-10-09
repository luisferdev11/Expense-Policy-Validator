"""The 13 synthetic engine cases (DRAFT until Luis's review, SC-010).

A failing case is resolved against the policy text, never by editing the expected value to
match the code; resolutions are recorded in fixtures/CONVERSION_NOTES.md.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from expense_validator.engine.context import build_context
from expense_validator.engine.evaluate import RULES
from expense_validator.models import ClassifiedReceipt, ReceiptInput
from tests.engine_cases.helpers import run, settings
from tests.factories import cls

FIXTURES = Path(__file__).parent / "fixtures" / "engine_cases.jsonl"
CASES: list[dict[str, Any]] = [
    json.loads(line) for line in FIXTURES.read_text(encoding="utf-8").splitlines() if line
]


def _classified(entry: dict[str, Any]) -> ClassifiedReceipt:
    receipt = ReceiptInput.model_validate(entry["receipt"])
    return ClassifiedReceipt(
        receipt=receipt,
        classifications=tuple(
            cls(
                c["line_id"],
                c["category"],
                confidence=c["confidence"],
                subtype=c["subtype"],
                recipient_kind=c["recipient_kind"],
                recipient_name=c["recipient_name"],
            )
            for c in entry["classifications"]
        ),
    )


def test_every_expected_rule_exists() -> None:
    needed = {e["rule_id"] for c in CASES for e in c["expected"]["exceptions"]}
    needed |= {s["rule_id"] for c in CASES for s in c["expected"]["review_signals"]}
    assert needed <= set(RULES)


@pytest.mark.parametrize("case", CASES, ids=[c["case_id"] for c in CASES])
def test_case(case: dict[str, Any]) -> None:
    batch = [_classified(entry) for entry in case["receipts"]]
    findings = run(batch[0], context=build_context(batch, settings()))
    expected = case["expected"]
    got = sorted((e.rule_id, e.severity, tuple(e.line_ids)) for e in findings.exceptions)
    want = sorted(
        (e["rule_id"], e["severity"], tuple(e["line_ids"])) for e in expected["exceptions"]
    )
    assert got == want
    assert sorted(s.rule_id for s in findings.review_signals) == sorted(
        s["rule_id"] for s in expected["review_signals"]
    )
    assert findings.disposition == expected["disposition"]
