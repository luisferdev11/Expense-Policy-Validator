"""MCC-01, MCC-02 and MCC-03 (T050, FR-020)."""

import pytest

from tests.unit.rule_helpers import exc, ids, one, signals


@pytest.mark.parametrize("mcc", [5921, 5993, 7995, 7297, 5944])
def test_mcc_01_high_risk_is_a_receipt_level_high_exception(mcc: int) -> None:
    f = one(["office_supplies"], mcc=mcc)
    assert exc(f, "MCC-01").severity == "high"
    assert exc(f, "MCC-01").line_ids == []


@pytest.mark.parametrize("mcc", [5813, 5912, 5311, 5411, 5732])
def test_mcc_02_is_always_its_own_signal(mcc: int) -> None:
    f = one(["personal_electronics"], mcc=mcc)
    assert "MCC-02" in signals(f)
    assert "MCC-02" not in ids(f)
    assert "TECH-01" in ids(f)


def test_unlisted_mcc_is_low_risk() -> None:
    f = one(["office_supplies"], mcc=1234)
    assert "MCC-01" not in ids(f)
    assert "MCC-02" not in signals(f)


def test_mcc_03_bar_is_on_premises() -> None:
    f = one(["alcohol"], mcc=5813, submitted_expense_type="Meals - Individual")
    assert "ALC-01" in ids(f)
    assert "ALC-03" not in ids(f)
