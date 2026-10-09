"""Template reporter: explanations state the rule, the lines and the arithmetic (T035, FR-022)."""

from expense_validator.engine.registry import REGISTRY
from expense_validator.models import EngineFindings, ExceptionFinding, ReviewSignal, RunMetadata
from expense_validator.reporter import report
from tests.factories import classified, item, receipt

RUN = RunMetadata(
    classifier="hand",
    model_id="hand-written",
    provider_endpoint="none",
    prompt_version="test",
    rules_version="000000000000",
    exc03_threshold=0.5,
    exc03_threshold_status="provisional",
)


def tech02() -> ExceptionFinding:
    spec = REGISTRY["TECH-02"]
    return ExceptionFinding(
        rule_id="TECH-02",
        policy_doc=spec.policy_doc,
        severity="medium",
        line_ids=["SYN-1-L1"],
        evidence=spec.evidence,
        explanation="",
        decisions=list(spec.decisions),
        computed={"unit_price_usd": "329.00", "cap_usd": "200.00"},
    )


def test_tech_02_explanation_has_rule_line_and_arithmetic() -> None:
    r = classified(receipt([item(1, description="Monitor", amount="329.00")]), "computer_accessory")
    findings = EngineFindings(exceptions=(tech02(),), review_signals=(), disposition="flag")
    result = report(r, findings, RUN)
    (exc,) = result.exceptions
    assert "TECH-02" in exc.explanation
    assert "SYN-1-L1" in exc.explanation
    assert "$329.00" in exc.explanation
    assert "$200.00" in exc.explanation


def test_explanation_only_uses_computed_values() -> None:
    r = classified(receipt([item(1, amount="329.00")]), "computer_accessory")
    finding = tech02().model_copy(
        update={"computed": {"unit_price_usd": "1.23", "cap_usd": "4.56"}}
    )
    result = report(
        r, EngineFindings(exceptions=(finding,), review_signals=(), disposition="flag"), RUN
    )
    assert "$1.23" in result.exceptions[0].explanation
    assert "329" not in result.exceptions[0].explanation


def test_mcc_02_signal_gets_a_reason() -> None:
    r = classified(receipt([item(1)], mcc=5411, mcc_description="Grocery stores"), "food_beverage")
    signal = ReviewSignal(rule_id="MCC-02", policy_doc="merchant-category-risk.md", reason="")
    result = report(
        r, EngineFindings(exceptions=(), review_signals=(signal,), disposition="review"), RUN
    )
    assert "5411" in result.review_signals[0].reason
    assert "not an exception" in result.review_signals[0].reason


def test_result_carries_lines_and_run_metadata() -> None:
    r = classified(receipt([item(1, description="Notebook")]), "office_supplies")
    result = report(r, EngineFindings(exceptions=(), review_signals=(), disposition="pass"), RUN)
    assert result.receipt_id == "SYN-1"
    assert result.line_items[0].category == "office_supplies"
    assert result.line_items[0].description_raw == "Notebook"
    assert result.run.exc03_threshold_status == "provisional"
