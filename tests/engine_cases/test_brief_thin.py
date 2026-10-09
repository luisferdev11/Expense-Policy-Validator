"""Brief cases for the thin path: threshold boundary and a review signal alone (T031).

Expected behaviour comes from the brief's text:
- "A $189 dock passes; a $329 monitor without pre-approval does not" (RCP-006, RCP-026);
- "A medium-risk MCC with compliant items gives review with no exceptions" (RCP-028).
"""

from tests.engine_cases.helpers import hand, rule_ids, run, signal_ids


def test_189_dock_raises_no_tech_02() -> None:
    findings = run(hand("RCP-006", "computer_accessory"))
    assert "TECH-02" not in rule_ids(findings)


def test_329_monitor_without_pre_approval_raises_tech_02() -> None:
    findings = run(hand("RCP-026", "computer_accessory", "computer_accessory"))
    (tech02,) = [e for e in findings.exceptions if e.rule_id == "TECH-02"]
    assert tech02.severity == "medium"
    assert tech02.line_ids == ["RCP-026-L1"]
    assert tech02.computed["unit_price_usd"] == "329.00"
    assert findings.disposition == "flag"


def test_medium_risk_mcc_alone_gives_review() -> None:
    findings = run(hand("RCP-028", "health_otc", "health_otc"))
    assert findings.exceptions == ()
    assert signal_ids(findings) == {"MCC-02"}
    assert findings.disposition == "review"
