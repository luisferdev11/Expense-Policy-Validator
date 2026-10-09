"""The brief's five unit-test cases on the full engine (T066, SC-002).

Receipts come through the loader (answers stripped). Classifications are written by hand from
each line's description. Expected behaviour comes from the brief's text only:
- RCP-027: "Clothing with no baggage-delay reference is still an exception";
- RCP-016: "The APAC alcohol rule applies even though the global rules would allow it";
- RCP-006 / RCP-026: "A $189 dock passes; a $329 monitor without pre-approval does not";
- RCP-031: "A single low-severity exception gives review, not flag";
- RCP-028: "A medium-risk MCC with compliant items gives review with no exceptions".
"""

from tests.engine_cases.helpers import hand, rule_ids, run, signal_ids


def test_carve_out_without_evidence_rcp_027() -> None:
    # "Men's dress shirt", "Dress socks 3-pack": clothing, no baggage-delay reference.
    findings = run(hand("RCP-027", "clothing", "clothing"))
    assert "PERS-02" in rule_ids(findings)
    (pers02,) = [e for e in findings.exceptions if e.rule_id == "PERS-02"]
    assert pers02.line_ids == ["RCP-027-L1", "RCP-027-L2"]
    assert findings.disposition == "flag"


def test_regional_override_rcp_016() -> None:
    # "Thali dinner", "Kingfisher beer 650ml", "Service charge"; APAC employee, 3 attendees.
    findings = run(hand("RCP-016", "food_beverage", "alcohol", "service_fee"))
    assert "REG-01" in rule_ids(findings)
    assert not {"ALC-01", "ALC-02", "ALC-03"} & rule_ids(findings)
    (reg01,) = [e for e in findings.exceptions if e.rule_id == "REG-01"]
    assert (reg01.severity, reg01.line_ids) == ("high", ["RCP-016-L2"])


def test_threshold_boundary_rcp_006_and_rcp_026() -> None:
    dock = run(hand("RCP-006", "computer_accessory"))
    assert "TECH-02" not in rule_ids(dock)
    assert dock.disposition == "pass"
    monitor = run(hand("RCP-026", "computer_accessory", "computer_accessory"))
    assert "TECH-02" in rule_ids(monitor)
    assert monitor.disposition == "flag"


def test_severity_ladder_rcp_031() -> None:
    # "Limpeza a seco - 2 camisas": laundry on a 2-night trip, a single low exception.
    findings = run(hand("RCP-031", "laundry_service"))
    assert {e.severity for e in findings.exceptions} == {"low"}
    assert findings.disposition == "review"


def test_review_signal_on_its_own_rcp_028() -> None:
    # "Ibuprofen 200mg 24ct", "Throat lozenges": OTC on a trip, under $25, at a pharmacy.
    findings = run(hand("RCP-028", "health_otc", "health_otc"))
    assert findings.exceptions == ()
    assert signal_ids(findings) == {"MCC-02"}
    assert findings.disposition == "review"
