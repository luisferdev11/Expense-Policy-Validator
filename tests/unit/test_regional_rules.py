"""REG-01..05: regional overrides (T062, FR-015, A1, A2)."""

from decimal import Decimal as D

from tests.engine_cases.helpers import run
from tests.factories import classified, item, receipt
from tests.unit.rule_helpers import exc, ids, one, signals


def test_reg_01_apac_alcohol_replaces_alc_rules_but_not_mcc_01() -> None:
    f = one(
        ["food_beverage", "alcohol"],
        entity="APAC",
        employee_country="IN",
        mcc=5921,
        submitted_expense_type="Client Entertainment",
        attendee_count=3,
    )
    assert exc(f, "REG-01").severity == "high"
    assert exc(f, "REG-01").line_ids == ["SYN-1-L2"]
    assert not {"ALC-01", "ALC-02", "ALC-03"} & ids(f)
    assert "MCC-01" in ids(f)


def test_reg_02_apac_60_per_person_replaces_meal_01() -> None:
    f = one(
        ["food_beverage"],
        amounts=["61.00"],
        entity="APAC",
        employee_country="SG",
        submitted_expense_type="Meals - Individual",
    )
    assert exc(f, "REG-02").severity == "medium"
    assert exc(f, "REG-02").line_ids == []
    assert "MEAL-01" not in ids(f)


def test_reg_03_emea_eur_70_at_the_receipt_rate_replaces_meal_01() -> None:
    def emea(amount: str) -> object:
        r = receipt(
            [item(1, amount=amount, fx="1.08")],
            entity="EMEA",
            employee_country="DE",
            currency="EUR",
            fx_rate_to_usd=D("1.08"),
            submitted_expense_type="Meals - Individual",
        )
        return classified(r, "food_beverage")

    over = run(emea("71.00"))
    assert exc(over, "REG-03").severity == "medium"
    assert exc(over, "REG-03").computed["cap_usd"] == "75.60"
    assert "MEAL-01" not in ids(over)
    assert "REG-03" not in ids(run(emea("70.00")))


def test_reg_04_emea_above_eur_50_without_vat_is_low_a2() -> None:
    fields = {
        "entity": "EMEA",
        "employee_country": "FR",
        "currency": "EUR",
        "fx_rate_to_usd": "1.08",
    }
    f = one(["office_supplies"], amounts=["51.00"], **fields)
    assert exc(f, "REG-04").severity == "low"
    assert exc(f, "REG-04").line_ids == []
    assert "REG-04" not in ids(one(["office_supplies"], amounts=["50.00"], **fields))
    assert "REG-04" not in ids(
        one(["office_supplies"], amounts=["51.00"], vat_number="FR1", **fields)
    )


def test_reg_04_non_eur_receipt_without_a_euro_rate_goes_to_review_a1() -> None:
    f = one(
        ["office_supplies"],
        amounts=["60.00"],
        entity="EMEA",
        employee_country="GB",
        currency="GBP",
        fx_rate_to_usd=D("1.27"),
        transaction_datetime="2026-05-01T12:00:00",
    )
    # config/eur_rates.csv has no row for 2026-05-01, so the euro rate is unknown.
    assert "REG-04" not in ids(f)
    assert "REG-04" in signals(f)
    assert f.disposition != "pass"


def test_reg_05_raises_nothing_on_its_own() -> None:
    f = one(["office_supplies"], currency="EUR", fx_rate_to_usd=D("1.08"))
    assert "REG-05" not in ids(f) | signals(f)
