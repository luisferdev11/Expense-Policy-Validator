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


def _params() -> list[Any]:
    params = []
    for case in CASES:
        expected = case["expected"]
        needed = {e["rule_id"] for e in expected["exceptions"]}
        needed |= {s["rule_id"] for s in expected["review_signals"]}
        missing = needed - set(RULES)
        marks = (
            [pytest.mark.xfail(strict=True, reason=f"rules not implemented yet: {sorted(missing)}")]
            if missing
            else []
        )
        params.append(pytest.param(case, id=case["case_id"], marks=marks))
    return params


@pytest.mark.parametrize("case", _params())
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
