"""Reviewer rules: reason codes, agreement and the human classification (ADR 0007 D8 to D10)."""

from __future__ import annotations

import pytest

from expense_validator.domain.lifecycle import ACTIONS, state_after_correction
from expense_validator.domain.models import Classification
from expense_validator.domain.review import (
    REASON_CODES,
    agreement,
    apply_corrections,
    human_classification,
    requires_reason,
)
from expense_validator.domain.taxonomy import CATEGORIES, restricted_for
from tests.factories import cls, unclassified


def test_a_reason_is_required_exactly_when_the_decision_overrides_the_proposal() -> None:
    assert requires_reason("approve", "flag") is True
    assert requires_reason("reject", "pass") is True
    for proposal in ("pass", "review"):
        assert requires_reason("approve", proposal) is False  # type: ignore[arg-type]
    for proposal in ("flag", "review"):
        assert requires_reason("reject", proposal) is False  # type: ignore[arg-type]
    for action in ("correct-category", "request-info", "escalate"):
        for proposal in ("pass", "review", "flag"):
            assert requires_reason(action, proposal) is False  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("action", "proposal", "expected"),
    [
        ("approve", "pass", 1),
        ("approve", "review", 1),
        ("approve", "flag", 0),
        ("reject", "flag", 1),
        ("reject", "review", 1),
        ("reject", "pass", 0),
        ("request-info", "review", 1),
        ("request-info", "flag", 1),
        ("request-info", "pass", 0),
        ("escalate", "review", 1),
        ("escalate", "flag", 1),
        ("escalate", "pass", 0),
        ("correct-category", "pass", 0),
        ("correct-category", "review", 0),
        ("correct-category", "flag", 0),
    ],
)
def test_the_agreement_table(action: str, proposal: str, expected: int) -> None:
    assert agreement(action, proposal) == expected  # type: ignore[arg-type]


def test_every_action_has_an_agreement_for_every_proposal() -> None:
    for action in ACTIONS:
        for proposal in ("pass", "review", "flag"):
            assert agreement(action, proposal) in (0, 1)  # type: ignore[arg-type]


def test_the_reason_codes_are_a_closed_list() -> None:
    assert set(REASON_CODES) == {
        "policy_exception_granted",
        "engine_false_positive",
        "engine_missed_issue",
        "documentation_provided",
        "other",
    }


def test_a_human_classification_is_certain_and_sourced_to_the_auditor() -> None:
    model = cls("L1", "office_supplies", confidence=0.4)
    human = human_classification(model, "alcohol", "R-1", 2, 77)
    assert human.status == "classified" and human.category == "alcohol"
    assert human.confidence == 1.0
    assert human.restricted is restricted_for("alcohol") is True
    assert human.source.classifier == "auditor" and human.source.model_id == "human"
    assert human.source.cache_key == "auditor:R-1:2:L1:77"
    assert human.line_id == "L1"


def test_subtype_survives_only_while_the_category_is_other() -> None:
    model = cls("L1", "other", subtype="event_ticket")
    assert human_classification(model, "other", "R", 1, 1).subtype == "event_ticket"
    assert human_classification(model, "gift", "R", 1, 1).subtype == "none"


def test_the_recipient_is_kept_because_gift_rules_read_it() -> None:
    model = cls("L1", "gift", recipient_kind="government_official", recipient_name="Official")
    human = human_classification(model, "gift_card", "R", 1, 1)
    assert (human.recipient_kind, human.recipient_name) == ("government_official", "Official")


def test_an_unclassified_line_can_be_given_a_category() -> None:
    human = human_classification(unclassified("L1"), "food_beverage", "R", 1, 1)
    assert human.status == "classified" and human.unclassified_reason is None


def test_every_taxonomy_category_is_accepted_and_others_are_not() -> None:
    for category in CATEGORIES:
        assert human_classification(cls("L1", "other"), category, "R", 1, 1).category == category
    with pytest.raises(ValueError, match="category"):
        human_classification(cls("L1", "other"), "spaceship", "R", 1, 1)


def test_the_latest_correction_of_a_line_wins_and_other_lines_are_untouched() -> None:
    base: tuple[Classification, ...] = (cls("L1", "office_supplies"), cls("L2", "lodging"))
    corrected = apply_corrections(
        base, "R", 1, [(5, "L1", "alcohol"), (9, "L1", "gift"), (7, "L9", "clothing")]
    )
    assert [c.category for c in corrected] == ["gift", "lodging"]
    assert corrected[0].source.cache_key == "auditor:R:1:L1:9"
    assert corrected[1] is base[1]
    assert apply_corrections(base, "R", 1, []) == base


def test_after_a_correction_the_receipt_waits_for_a_human_even_if_it_now_passes() -> None:
    assert state_after_correction("auto_approved") == "in_review"
    assert state_after_correction("in_review") == "in_review"
    assert state_after_correction("compliance") == "compliance"
