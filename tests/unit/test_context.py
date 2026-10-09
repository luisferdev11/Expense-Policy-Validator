"""Cross-receipt context (T056, FR-021, A8)."""

import random
from decimal import Decimal as D

from expense_validator.adapters.config_files import load_settings
from expense_validator.domain.engine.context import build_context, day_key
from tests.factories import classified, cls, item, receipt

S = load_settings()


def meal(rid: str, amounts: list[str], cats: list[str], **fields: object) -> object:
    items = [item(i + 1, receipt_id=rid, amount=a) for i, a in enumerate(amounts)]
    base: dict[str, object] = {"receipt_id": rid, "submitted_expense_type": "Meals - Team"}
    return classified(receipt(items, **(base | fields)), *cats)


def test_meal_spend_counts_food_alcohol_and_gratuity_only() -> None:
    r = meal("SYN-M", ["30", "10", "5", "20"], ["food_beverage", "alcohol", "service_fee", "gift"])
    ctx = build_context([r], S)
    (c,) = ctx.meal_days[day_key("E-1", r.receipt.transaction_datetime)]
    assert c.per_person_usd == D("45")


def test_per_person_uses_attendees_or_one() -> None:
    r = meal("SYN-P", ["90"], ["food_beverage"], attendee_count=3)
    (c,) = build_context([r], S).meal_days[day_key("E-1", r.receipt.transaction_datetime)]
    assert c.per_person_usd == D("30")


def test_non_itemized_meal_uses_the_total() -> None:
    r = meal("SYN-N", ["64"], ["other"], itemized=False)
    (c,) = build_context([r], S).meal_days[day_key("E-1", r.receipt.transaction_datetime)]
    assert c.per_person_usd == D("64")


def test_non_meal_types_and_meal_types_without_food_are_left_out() -> None:
    office = meal("SYN-O", ["30"], ["food_beverage"], submitted_expense_type="Office Supplies")
    no_food = meal("SYN-F", ["30"], ["gift"])
    assert build_context([office, no_food], S).meal_days == {}


def test_same_employee_same_date_adds_up_and_international_is_by_home_currency() -> None:
    a = meal("SYN-1", ["40"], ["food_beverage"])
    b = meal("SYN-2", ["5000"], ["food_beverage"], currency="JPY", fx_rate_to_usd=D("0.0067"))
    day = build_context([a, b], S).meal_days[day_key("E-1", a.receipt.transaction_datetime)]
    assert [c.receipt_id for c in day] == ["SYN-1", "SYN-2"]
    assert [c.international for c in day] == [False, True]


def test_trip_otc_total_excludes_uncertain_items() -> None:
    r = classified(
        receipt([item(1, amount="15"), item(2, amount="30")], trip_id="T1"),
        "health_otc",
        cls("SYN-1-L2", "health_otc", confidence=0.2),
    )
    assert build_context([r], S).trip_otc_usd == {"T1": D("15")}


def test_shuffled_input_gives_an_identical_context() -> None:
    batch = [meal(f"SYN-{i}", [str(10 * i)], ["food_beverage"]) for i in range(1, 8)]
    shuffled = batch[:]
    random.Random(7).shuffle(shuffled)
    assert build_context(batch, S) == build_context(shuffled, S)
