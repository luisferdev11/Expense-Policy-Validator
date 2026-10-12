"""The two failure cases of the evaluation: real receipts, each with the stage that caused it.

The brief asks for two receipts the system got wrong, the stage that caused each (translation,
classification, retrieval or rule logic) and what would change. They are reviewed text kept in
`eval/failure_cases.py`, so the report states them instead of a placeholder.
"""

from __future__ import annotations

from eval.failure_cases import FAILURE_CASES, STAGES, render_failure_cases
from eval.scope import OUT_OF_SCOPE


def test_there_are_exactly_two_failure_cases() -> None:
    assert len(FAILURE_CASES) == 2
    assert len({c.receipt_id for c in FAILURE_CASES}) == 2


def test_each_case_names_a_stage_the_brief_allows() -> None:
    assert set(STAGES) == {"translation", "classification", "retrieval", "rule_logic"}
    for case in FAILURE_CASES:
        assert case.stage in STAGES


def test_each_case_is_a_scored_receipt_and_says_what_happened_and_what_would_change() -> None:
    for case in FAILURE_CASES:
        assert case.receipt_id not in OUT_OF_SCOPE
        assert case.run and case.cause and case.what_happened and case.change and case.evidence
        assert len(case.what_happened) > 80 and len(case.change) > 40


def test_the_rendered_section_has_no_placeholder_and_cites_each_receipt_and_stage() -> None:
    text = "\n".join(render_failure_cases(FAILURE_CASES))
    assert "TBD" not in text
    for case in FAILURE_CASES:
        assert case.receipt_id in text and case.stage in text and case.evidence in text
    assert text.count("**Failure case") == 2
