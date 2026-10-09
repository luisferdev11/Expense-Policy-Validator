"""TECH-01 to TECH-04 (T052, FR-013, FR-014, A5, A6)."""

from tests.factories import cls, item
from tests.unit.rule_helpers import engine, exc, ids, one


def test_tech_01_personal_electronics_high() -> None:
    f = one(["personal_electronics", "office_supplies"])
    assert exc(f, "TECH-01").severity == "high"
    assert exc(f, "TECH-01").line_ids == ["SYN-1-L1"]


def test_tech_02_boundary_and_pre_approval() -> None:
    at_cap = engine([item(1, amount="200.00")], ["computer_accessory"])
    assert "TECH-02" not in ids(at_cap)
    above = engine([item(1, amount="200.01")], ["computer_accessory"])
    assert exc(above, "TECH-02").severity == "medium"
    approved = engine(
        [item(1, amount="329.00")], ["computer_accessory"], pre_approval_ref="PA-2026-0001"
    )
    assert "TECH-02" not in ids(approved)


def test_tech_02_uses_unit_price_in_usd() -> None:
    two_cheap = engine([item(1, amount="320.00", quantity="2")], ["computer_accessory"])
    assert "TECH-02" not in ids(two_cheap)
    foreign = engine(
        [item(1, amount="20000", fx="0.012")],
        ["computer_accessory"],
        currency="INR",
        fx_rate_to_usd="0.012",
    )
    assert exc(foreign, "TECH-02").computed["unit_price_usd"] == "240.00"


def test_tech_03_mobile_handset_high() -> None:
    f = one([cls("SYN-1-L1", "other", subtype="mobile_handset")])
    assert exc(f, "TECH-03").severity == "high"


def test_tech_03_not_for_other_without_subtype() -> None:
    assert "TECH-03" not in ids(one(["other"]))


def test_tech_04_software_low_and_pa_does_not_satisfy_it() -> None:
    f = one(["software_subscription"], pre_approval_ref="PA-2026-0002")
    assert exc(f, "TECH-04").severity == "low"
    assert exc(f, "TECH-04").line_ids == ["SYN-1-L1"]
