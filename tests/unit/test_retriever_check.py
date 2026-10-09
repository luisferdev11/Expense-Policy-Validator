"""The retriever comparison (research R9): trigger map versus every rule, outcomes only."""

from __future__ import annotations

from eval.experiments.retriever_check import compare
from expense_validator.domain.models import ClassifiedReceipt, RuleSet
from tests.engine_cases.helpers import settings
from tests.factories import classified, item, receipt


def _alcohol() -> ClassifiedReceipt:
    r = receipt(
        [item(1, description="Red wine bottle", amount="40.00")],
        submitted_expense_type="Client Entertainment",
    )
    return classified(r, "alcohol")


def test_identical_outcomes_give_no_difference() -> None:
    out = compare([_alcohol()], settings())
    assert out == {"cases": 1, "differences": 0, "details": []}


def test_a_rule_the_trigger_map_misses_is_a_difference() -> None:
    batch = [_alcohol()]
    out = compare(batch, settings(), retriever=lambda r: RuleSet(rule_ids=()))
    assert out["cases"] == 1
    assert out["differences"] == 1
    detail = out["details"][0]
    assert detail["receipt_id"] == "SYN-1"
    assert detail["trigger_map"] != detail["all_rules"]
