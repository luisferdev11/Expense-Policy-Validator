"""DOC-01 to DOC-04 (T048). All whole-receipt rules cite empty line_ids."""

from decimal import Decimal as D

from tests.factories import item
from tests.unit.rule_helpers import engine, exc, ids, one


def test_doc_01_non_itemized_above_75() -> None:
    f = engine([item(1, amount="80.00")], ["other"], itemized=False)
    assert exc(f, "DOC-01").severity == "medium"
    assert exc(f, "DOC-01").line_ids == []


def test_doc_01_not_at_or_below_75_or_itemized() -> None:
    assert "DOC-01" not in ids(engine([item(1, amount="75.00")], ["other"], itemized=False))
    assert "DOC-01" not in ids(one(["office_supplies"], amounts=["80.00"]))


def test_doc_02_missing_merchant_date_or_total() -> None:
    for field in ("merchant_name", "transaction_datetime", "total_amount"):
        f = one(["office_supplies"], **{field: None})
        assert exc(f, "DOC-02").severity == "medium", field
        assert exc(f, "DOC-02").line_ids == []
    assert "DOC-02" not in ids(one(["office_supplies"]))


def test_doc_03_no_line_covered_by_the_declared_type() -> None:
    f = one(["computer_accessory", "service_fee"], submitted_expense_type="Software")
    assert exc(f, "DOC-03").severity == "medium"
    assert exc(f, "DOC-03").line_ids == []


def test_doc_03_one_covered_line_is_enough() -> None:
    f = one(["computer_accessory", "office_supplies"], submitted_expense_type="Office Supplies")
    assert "DOC-03" not in ids(f)


def test_doc_03_ignores_fees_and_other_and_skips_when_nothing_remains() -> None:
    f = one(["service_fee", "other"], submitted_expense_type="Software")
    assert "DOC-03" not in ids(f)


def test_doc_04_foreign_receipt_missing_rate_or_currency() -> None:
    f = one(["office_supplies"], currency="EUR", fx_rate_to_usd=None)
    assert exc(f, "DOC-04").severity == "medium"
    f = one(["office_supplies"], currency=None, fx_rate_to_usd=D("1.08"))
    assert "DOC-04" in ids(f)
    assert "DOC-04" not in ids(one(["office_supplies"], currency="EUR", fx_rate_to_usd=D("1.08")))
    assert "DOC-04" not in ids(one(["office_supplies"]))
