"""MEAL-01, MEAL-02, ALC-01..03, ENT-01, ENT-02 (T058, FR-014)."""

from decimal import Decimal as D

from tests.engine_cases.helpers import run
from tests.factories import classified, cls, item, receipt
from tests.unit.rule_helpers import engine, exc, ids, one


def meal_receipt(rid: str, amount: str, **fields: object) -> object:
    base: dict[str, object] = {"receipt_id": rid, "submitted_expense_type": "Meals - Individual"}
    return classified(
        receipt([item(1, receipt_id=rid, amount=amount)], **(base | fields)), "food_beverage"
    )


def test_meal_01_breached_day_flags_every_contributing_receipt() -> None:
    a, b = meal_receipt("SYN-A", "40"), meal_receipt("SYN-B", "50")
    for r in (a, b):
        finding = exc(run(r, batch=[a, b]), "MEAL-01")
        assert finding.severity == "medium"
        assert finding.line_ids == []
        assert finding.computed["cap_usd"] == "75.00"


def test_meal_01_international_cap_and_mixed_day_uses_the_higher_cap() -> None:
    a = meal_receipt("SYN-A", "40")
    b = meal_receipt("SYN-B", "8000", currency="JPY", fx_rate_to_usd=D("0.0067"))
    assert "MEAL-01" not in ids(run(a, batch=[a, b]))  # 40 + 53.60 <= 100


def test_meal_01_not_above_the_cap() -> None:
    assert "MEAL-01" not in ids(run(meal_receipt("SYN-A", "75")))


def test_meal_02_large_meal_without_attendees_is_low() -> None:
    f = engine(
        [item(1, amount="151.00")],
        ["food_beverage"],
        submitted_expense_type="Meals - Team",
        attendee_count=None,
    )
    assert exc(f, "MEAL-02").severity == "low"
    assert exc(f, "MEAL-02").line_ids == []
    with_count = engine(
        [item(1, amount="151.00")],
        ["food_beverage"],
        submitted_expense_type="Meals - Team",
        attendee_count=3,
    )
    assert "MEAL-02" not in ids(with_count)


def test_alc_01_alcohol_outside_client_entertainment_is_high_and_skips_the_tip() -> None:
    f = one(
        ["food_beverage", "alcohol", "service_fee"],
        mcc=5812,
        submitted_expense_type="Meals - Individual",
    )
    assert exc(f, "ALC-01").severity == "high"
    assert exc(f, "ALC-01").line_ids == ["SYN-1-L2"]


def test_alc_01_needs_two_or_more_attendees() -> None:
    f = one(["alcohol"], mcc=5812, submitted_expense_type="Client Entertainment", attendee_count=1)
    assert "ALC-01" in ids(f)
    ok = one(["alcohol"], mcc=5812, submitted_expense_type="Client Entertainment", attendee_count=2)
    assert "ALC-01" not in ids(ok)


def test_alc_02_above_30_per_attendee_is_medium() -> None:
    f = one(
        ["alcohol"],
        amounts=["61.00"],
        mcc=7011,
        submitted_expense_type="Client Entertainment",
        attendee_count=2,
    )
    assert exc(f, "ALC-02").severity == "medium"
    ok = one(
        ["alcohol"],
        amounts=["60.00"],
        mcc=7011,
        submitted_expense_type="Client Entertainment",
        attendee_count=2,
    )
    assert "ALC-02" not in ids(ok)


def test_alc_03_retail_alcohol_is_high_whatever_the_context() -> None:
    f = one(["alcohol"], mcc=5411, submitted_expense_type="Client Entertainment", attendee_count=4)
    assert exc(f, "ALC-03").severity == "high"
    assert "ALC-01" not in ids(f)


def test_ent_01_event_ticket_without_vp_approval() -> None:
    f = one([cls("SYN-1-L1", "other", subtype="event_ticket")], pre_approval_ref="PA-2026-9")
    assert exc(f, "ENT-01").severity == "medium"


def test_ent_02_gambling_is_high() -> None:
    assert exc(one(["gambling"]), "ENT-02").severity == "high"
