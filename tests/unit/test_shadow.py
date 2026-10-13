"""Comparing the deciding classifier with a shadow, and the agreement report (spec 007, T037).

Pure: synthetic classifications only, no store and no model."""

from __future__ import annotations

import pytest

from expense_validator.domain.shadow import (
    LineComparison,
    agreement,
    compare,
    proportion,
)
from expense_validator.domain.stats import wilson
from tests.factories import cls, unclassified


def test_a_line_agrees_when_the_category_is_the_same() -> None:
    primary = [cls("L1", "alcohol")]
    shadow = [cls("L1", "alcohol", confidence=0.7)]
    (c,) = compare(primary, shadow)
    assert (c.comparable, c.agrees_category, c.agrees_all) == (True, True, True)
    assert c.primary is primary[0] and c.shadow is shadow[0]


def test_a_different_category_disagrees_on_both() -> None:
    (c,) = compare([cls("L1", "alcohol")], [cls("L1", "food_beverage")])
    assert (c.comparable, c.agrees_category, c.agrees_all) == (True, False, False)


def test_the_same_category_with_another_subtype_or_recipient_kind_agrees_only_on_category() -> None:
    other = cls("L1", "other", subtype="event_ticket")
    (a,) = compare([cls("L1", "other")], [other])
    assert (a.agrees_category, a.agrees_all) == (True, False)
    (b,) = compare([cls("L1", "gift")], [cls("L1", "gift", recipient_kind="employee")])
    assert (b.agrees_category, b.agrees_all) == (True, False)


def test_recipient_names_are_compared_trimmed_and_casefolded() -> None:
    primary = [cls("L1", "gift", recipient_kind="client_or_prospect", recipient_name="Acme Corp")]
    same = [cls("L1", "gift", recipient_kind="client_or_prospect", recipient_name="  ACME corp ")]
    other = [cls("L1", "gift", recipient_kind="client_or_prospect", recipient_name="Beta Ltd")]
    missing = [cls("L1", "gift", recipient_kind="client_or_prospect", recipient_name=None)]
    assert compare(primary, same)[0].agrees_all is True
    assert compare(primary, other)[0].agrees_all is False
    assert compare(primary, missing)[0].agrees_all is False
    assert compare(missing, [cls("L1", "gift", recipient_kind="client_or_prospect")])[0].agrees_all


def test_a_line_that_either_side_could_not_classify_is_counted_but_not_comparable() -> None:
    both = compare(
        [cls("L1", "alcohol"), unclassified("L2"), cls("L3", "gift")],
        [unclassified("L1", "budget_refused"), cls("L2", "alcohol"), cls("L3", "gift")],
    )
    assert [c.comparable for c in both] == [False, False, True]
    assert [(c.agrees_category, c.agrees_all) for c in both[:2]] == [(False, False)] * 2


def test_only_lines_both_sides_have_are_compared_in_the_deciding_classifiers_order() -> None:
    result = compare(
        [cls("L1", "alcohol"), cls("L2", "gift"), cls("L3", "tobacco")],
        [cls("L3", "tobacco"), cls("L1", "alcohol")],  # L2 has no shadow row, and the order differs
    )
    assert [c.line_id for c in result] == ["L1", "L3"]


def test_a_proportion_carries_k_n_the_rate_and_the_wilson_interval() -> None:
    p = proportion(7, 10)
    assert (p.k, p.n) == (7, 10)
    assert p.rate == pytest.approx(0.7)
    assert p.interval == wilson(7, 10)
    empty = proportion(0, 0)
    assert (empty.rate, empty.interval) == (None, None)


def comparisons() -> list[tuple[str, list[LineComparison]]]:
    """Two receipts, six lines: four agree on the category, one disagrees, one is not comparable."""
    first = compare(
        [cls("A-1", "alcohol"), cls("A-2", "food_beverage"), cls("A-3", "other")],
        [cls("A-1", "alcohol"), cls("A-2", "alcohol"), cls("A-3", "other", subtype="event_ticket")],
    )
    second = compare(
        [cls("B-1", "gift"), cls("B-2", "gift"), cls("B-3", "tobacco")],
        [cls("B-1", "gift"), unclassified("B-2", "gateway_error"), cls("B-3", "tobacco")],
    )
    return [("A", first), ("B", second)]


def test_the_report_counts_agreement_over_the_comparable_lines_with_their_n() -> None:
    report = agreement(comparisons(), {})
    assert (report.receipts, report.lines, report.comparable) == (2, 6, 5)
    assert (report.category.k, report.category.n) == (4, 5)
    assert (report.restricted.k, report.restricted.n) == (4, 5)  # food_beverage vs alcohol differs
    assert (report.subtype.k, report.subtype.n) == (4, 5)  # A-3: none against event_ticket
    assert (report.recipient_kind.k, report.recipient_kind.n) == (5, 5)
    assert (report.all_fields.k, report.all_fields.n) == (3, 5)
    assert report.category.interval == wilson(4, 5)
    assert report.shadow_unclassified == {"gateway_error": 1}


def test_the_confusion_table_lists_the_category_disagreements_most_frequent_first() -> None:
    first = compare(
        [cls("A-1", "alcohol"), cls("A-2", "alcohol"), cls("A-3", "gift")],
        [cls("A-1", "food_beverage"), cls("A-2", "food_beverage"), cls("A-3", "tobacco")],
    )
    report = agreement([("A", first)], {})
    assert [(c.primary, c.shadow, c.count) for c in report.confusion] == [
        ("alcohol", "food_beverage", 2),
        ("gift", "tobacco", 1),
    ]


def test_each_classifier_is_scored_against_the_reviewer_on_the_lines_a_reviewer_corrected() -> None:
    # the reviewer corrected A-2 to food_beverage (the primary was right) and B-3 to gift (neither
    # was); a line corrected where either side could not answer is left out of the comparison
    corrections = {("A", "A-2"): "food_beverage", ("B", "B-3"): "gift", ("B", "B-2"): "gift"}
    report = agreement(comparisons(), corrections)
    c = report.corrections
    assert (c.corrected_lines, c.n) == (3, 2)
    assert (c.primary.k, c.primary.n) == (1, 2)
    assert (c.shadow.k, c.shadow.n) == (0, 2)


def test_an_empty_store_reports_no_agreement_instead_of_dividing_by_zero() -> None:
    report = agreement([], {})
    assert (report.receipts, report.lines, report.comparable) == (0, 0, 0)
    assert report.category.rate is None and report.confusion == []
    assert (report.corrections.n, report.corrections.primary.rate) == (0, None)
