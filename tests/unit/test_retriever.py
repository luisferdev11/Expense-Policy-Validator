"""Deterministic trigger-map retriever (T033, FR-010)."""

from expense_validator.retriever import retrieve
from tests.factories import classified, item, receipt


def test_tech_02_for_a_computer_accessory() -> None:
    r = classified(receipt([item(1)]), "computer_accessory")
    assert "TECH-02" in retrieve(r).rule_ids


def test_no_tech_02_without_an_accessory() -> None:
    r = classified(receipt([item(1)]), "office_supplies")
    assert "TECH-02" not in retrieve(r).rule_ids


def test_mcc_02_for_a_medium_tier_mcc() -> None:
    r = classified(receipt([item(1)], mcc=5411, mcc_description="Grocery"), "food_beverage")
    assert "MCC-02" in retrieve(r).rule_ids


def test_output_is_a_sorted_tuple() -> None:
    r = classified(receipt([item(1)], mcc=5411), "computer_accessory")
    ids = retrieve(r).rule_ids
    assert isinstance(ids, tuple)
    assert list(ids) == sorted(ids)
