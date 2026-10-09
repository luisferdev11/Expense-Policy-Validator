"""The retriever never drops a rule the engine would raise (T067, FR-011)."""

from typing import Any

from expense_validator.domain.engine.context import build_context
from expense_validator.domain.engine.evaluate import RULES, evaluate
from expense_validator.domain.engine.registry import REGISTRY
from expense_validator.domain.models import Classification, ClassifiedReceipt, RuleSet
from expense_validator.domain.retriever import TRIGGERS, retrieve
from tests.engine_cases.helpers import settings
from tests.engine_cases.test_synthetic_cases import CASES, _classified
from tests.factories import classified, cls, item, receipt

ALL = RuleSet(rule_ids=tuple(sorted(REGISTRY)))


def test_every_firing_rule_has_a_trigger() -> None:
    assert set(RULES) <= set(TRIGGERS)


def test_superset_on_every_engine_fixture() -> None:
    for case in CASES:
        batch = [_classified(entry) for entry in case["receipts"]]
        context = build_context(batch, settings())
        for cr in batch:
            raised = evaluate(cr, context, ALL, settings())
            fired = {e.rule_id for e in raised.exceptions} | {
                s.rule_id for s in raised.review_signals
            }
            assert fired <= set(retrieve(cr).rule_ids), case["case_id"]


def _synthetic_receipts() -> list[ClassifiedReceipt]:
    """Receipts that together fire nearly every rule, each a single-receipt batch."""

    def r(cats: list[str | Classification], **fields: Any) -> ClassifiedReceipt:
        amounts = fields.pop("amounts", None) or ["120.00"] * len(cats)
        items = [item(i + 1, amount=a) for i, a in enumerate(amounts)]
        return classified(receipt(items, **fields), *cats)

    return [
        r(["alcohol"], mcc=5812, submitted_expense_type="Meals - Individual"),
        r(["alcohol"], mcc=5813, submitted_expense_type="Client Entertainment", attendee_count=2),
        r(["alcohol", "food_beverage"], mcc=5921, submitted_expense_type="Meals - Team"),
        r(
            ["alcohol", "food_beverage"],
            entity="APAC",
            employee_country="IN",
            mcc=5812,
            submitted_expense_type="Meals - Individual",
        ),
        r(
            ["food_beverage"],
            entity="EMEA",
            employee_country="DE",
            currency="EUR",
            fx_rate_to_usd="1.08",
            submitted_expense_type="Meals - Individual",
        ),
        r(
            ["office_supplies"],
            entity="EMEA",
            employee_country="GB",
            currency="GBP",
            fx_rate_to_usd="1.27",
        ),
        r(
            [
                cls("SYN-1-L1", "other", subtype="event_ticket"),
                cls("SYN-1-L2", "other", subtype="mobile_handset"),
                cls("SYN-1-L3", "other", subtype="prescription_medication"),
            ]
        ),
        r(["gambling", "personal_electronics", "computer_accessory", "software_subscription"]),
        r(
            [
                cls("SYN-1-L1", "gift", recipient_kind="client_or_prospect", recipient_name="Ana"),
                cls("SYN-1-L2", "gift_card"),
                cls("SYN-1-L3", "jewelry", recipient_kind="employee", recipient_name="Sam"),
                cls(
                    "SYN-1-L4",
                    "food_beverage",
                    recipient_kind="government_official",
                    recipient_name="Minister",
                ),
            ]
        ),
        r(
            [
                "personal_care",
                "clothing",
                "tobacco",
                "household_goods",
                "health_otc",
                "laundry_service",
            ]
        ),
        r(["other"], itemized=False, merchant_name=None, currency="EUR", fx_rate_to_usd=None),
        r(["computer_accessory"], submitted_expense_type="Software", mcc=5411),
        r([cls("SYN-1-L1", "office_supplies", confidence=0.1)]),
    ]


def test_superset_on_synthetic_receipts_covering_the_rules() -> None:
    fired_overall: set[str] = set()
    for receipt_ in _synthetic_receipts():
        context = build_context([receipt_], settings())
        raised = evaluate(receipt_, context, ALL, settings())
        fired = {e.rule_id for e in raised.exceptions} | {s.rule_id for s in raised.review_signals}
        assert fired <= set(retrieve(receipt_).rule_ids), receipt_.receipt.receipt_id
        fired_overall |= fired
    # The samples must actually exercise the retriever, not pass vacuously.
    assert len(fired_overall) >= 28, sorted(set(RULES) - fired_overall)
