"""EXC-03: uncertain items become a review signal and leave every calculation (T064)."""

from expense_validator.adapters.config_files import load_settings
from expense_validator.domain.engine.context import build_context
from expense_validator.domain.engine.evaluate import evaluate
from tests.engine_cases.helpers import ALL_RULES
from tests.factories import classified, cls, item, receipt, unclassified
from tests.unit.rule_helpers import engine, ids, one, signals


def test_low_confidence_gives_one_exc_03_citing_the_line() -> None:
    f = one([cls("SYN-1-L1", "alcohol", confidence=0.49), "office_supplies"])
    (signal,) = [s for s in f.review_signals if s.rule_id == "EXC-03"]
    assert signal.line_ids == ["SYN-1-L1"]
    assert "ALC-01" not in ids(f) and "ALC-03" not in ids(f)
    assert f.disposition == "review"


def test_threshold_is_inclusive_at_0_5() -> None:
    f = one([cls("SYN-1-L1", "office_supplies", confidence=0.5)])
    assert "EXC-03" not in signals(f)


def test_the_chosen_threshold_is_inclusive_at_0_95() -> None:
    real = load_settings()
    r = receipt([item(1)])
    for confidence, fires in ((0.95, False), (0.94, True)):
        cr = classified(r, cls("SYN-1-L1", "office_supplies", confidence=confidence))
        f = evaluate(cr, build_context([cr], real), ALL_RULES, real)
        assert ("EXC-03" in signals(f)) is fires


def test_unclassified_item_gives_exc_03_and_never_pass() -> None:
    f = one([unclassified("SYN-1-L1", "gateway_error")])
    assert "EXC-03" in signals(f)
    assert f.disposition != "pass"


def test_uncertain_item_leaves_doc_03_and_gift_caps() -> None:
    # Only the uncertain line is covered by "Software"; once it leaves, nothing is covered.
    f = one(
        [cls("SYN-1-L1", "software_subscription", confidence=0.3), "office_supplies"],
        submitted_expense_type="Software",
    )
    assert "DOC-03" in ids(f)
    gifts = one(
        [
            cls(
                "SYN-1-L1",
                "gift",
                confidence=0.2,
                recipient_kind="client_or_prospect",
                recipient_name="Ana",
            ),
            cls("SYN-1-L2", "gift", recipient_kind="client_or_prospect", recipient_name="Ana"),
        ],
        amounts=["40.00", "20.00"],
    )
    assert "GIFT-01" not in ids(gifts)


def test_non_itemized_other_is_not_uncertain() -> None:
    f = engine(
        [item(1, amount="40.00")], [cls("SYN-1-L1", "other", confidence=0.1)], itemized=False
    )
    assert "EXC-03" not in signals(f)
