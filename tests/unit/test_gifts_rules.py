"""GIFT-01..04 (T060, FR-006, A7, A9)."""

from tests.factories import cls
from tests.unit.rule_helpers import exc, ids, one


def gift(n: int, name: str | None = None, kind: str = "none", category: str = "gift") -> object:
    kind = kind if kind != "none" or name is None else "client_or_prospect"
    return cls(f"SYN-1-L{n}", category, recipient_kind=kind, recipient_name=name)


def test_gift_01_cap_per_named_recipient() -> None:
    f = one([gift(1, "Ana Ruiz"), gift(2, "Ana Ruiz")], amounts=["30.00", "25.00"])
    finding = exc(f, "GIFT-01")
    assert finding.severity == "medium"
    assert finding.line_ids == ["SYN-1-L1", "SYN-1-L2"]
    split = one([gift(1, "Ana Ruiz"), gift(2, "Bo Li")], amounts=["30.00", "25.00"])
    assert "GIFT-01" not in ids(split)


def test_gift_01_unnamed_gift_of_10_or_more_on_a_client_gifts_receipt() -> None:
    f = one([gift(1), gift(2)], amounts=["10.00", "9.99"], submitted_expense_type="Client Gifts")
    finding = exc(f, "GIFT-01")
    assert finding.line_ids == ["SYN-1-L1"]
    assert finding.evidence.startswith("Any gift of $10 or more must also name its recipient")


def test_gift_01_needs_a_client_gifts_receipt_or_a_named_line_a7() -> None:
    f = one([gift(1)], amounts=["80.00"], submitted_expense_type="Office Supplies")
    assert "GIFT-01" not in ids(f)


def test_gift_01_ignores_meal_lines_even_with_a_named_guest() -> None:
    f = one([gift(1, "Ana Ruiz", category="food_beverage")], amounts=["80.00"])
    assert "GIFT-01" not in ids(f)


def test_gift_02_gift_card_high_and_not_tested_under_gift_01() -> None:
    f = one([gift(1, "Ana Ruiz", category="gift_card")], amounts=["100.00"])
    assert exc(f, "GIFT-02").severity == "high"
    assert "GIFT-01" not in ids(f)


def test_gift_03_employee_recipient_is_medium() -> None:
    f = one([gift(1, "Sam Lee", kind="employee")], amounts=["40.00"])
    assert exc(f, "GIFT-03").severity == "medium"
    assert "GIFT-01" not in ids(f)


def test_gift_04_official_is_critical_covers_meals_not_gratuity_and_replaces_gift_01() -> None:
    f = one(
        [
            gift(1, "Vice-Minister Ortega", kind="government_official", category="food_beverage"),
            gift(2, "Vice-Minister Ortega", kind="government_official"),
            cls("SYN-1-L3", "service_fee"),
        ],
        amounts=["90.00", "70.00", "18.00"],
        submitted_expense_type="Client Entertainment",
        attendee_count=2,
    )
    finding = exc(f, "GIFT-04")
    assert finding.severity == "critical"
    assert finding.line_ids == ["SYN-1-L1", "SYN-1-L2"]
    assert "GIFT-01" not in ids(f)
