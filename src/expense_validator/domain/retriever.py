"""Policy retriever: a deterministic trigger map over items, MCC and metadata (research R10).

Each rule that can fire lists the conditions under which it could apply; a rule is selected when
its trigger matches. Triggers read every line, uncertain ones included, so the selection is a
superset of what the engine raises; a test checks that on every fixture (FR-011). The four
modifiers (EXC-01, EXC-02, EXC-04, MCC-03) and REG-05 never fire on their own and have no
trigger.
"""

from __future__ import annotations

from collections.abc import Callable

from expense_validator.domain.engine.context import MEAL_TYPES
from expense_validator.domain.engine.rules.merchant import HIGH_RISK_MCC, MEDIUM_RISK_MCC
from expense_validator.domain.models import ClassifiedReceipt, RuleSet

Trigger = Callable[[ClassifiedReceipt], bool]


def _categories(r: ClassifiedReceipt) -> set[str]:
    return {c.category for c in r.classifications if c.category is not None}


def _has(*categories: str) -> Trigger:
    return lambda r: bool(_categories(r) & set(categories))


def _subtype(subtype: str) -> Trigger:
    return lambda r: any(c.subtype == subtype for c in r.classifications)


def _recipient(kind: str) -> Trigger:
    return lambda r: any(c.recipient_kind == kind for c in r.classifications)


def _meal_type(r: ClassifiedReceipt) -> bool:
    return r.receipt.submitted_expense_type in MEAL_TYPES


def _entity(entity: str) -> Trigger:
    return lambda r: r.receipt.entity == entity


def _always(r: ClassifiedReceipt) -> bool:
    return True


TRIGGERS: dict[str, Trigger] = {
    "MEAL-01": _meal_type,
    "MEAL-02": _meal_type,
    "ALC-01": _has("alcohol"),
    "ALC-02": _has("alcohol"),
    "ALC-03": _has("alcohol"),
    "ENT-01": _subtype("event_ticket"),
    "ENT-02": _has("gambling"),
    "TECH-01": _has("personal_electronics"),
    "TECH-02": _has("computer_accessory"),
    "TECH-03": _subtype("mobile_handset"),
    "TECH-04": _has("software_subscription"),
    "GIFT-01": lambda r: (
        r.receipt.submitted_expense_type == "Client Gifts"
        or any(c.recipient_name for c in r.classifications)
    ),
    "GIFT-02": _has("gift_card"),
    "GIFT-03": _recipient("employee"),
    "GIFT-04": _recipient("government_official"),
    "PERS-01": _has("personal_care"),
    "PERS-02": _has("clothing"),
    "PERS-03": _has("tobacco"),
    "HOUSE-01": _has("household_goods"),
    "HEALTH-01": lambda r: "health_otc" in _categories(r) or _subtype("prescription_medication")(r),
    "LAUNDRY-01": _has("laundry_service"),
    "MCC-01": lambda r: r.receipt.mcc in HIGH_RISK_MCC,
    "MCC-02": lambda r: r.receipt.mcc in MEDIUM_RISK_MCC,
    "DOC-01": lambda r: not r.receipt.itemized,
    "DOC-02": _always,
    "DOC-03": _always,
    "DOC-04": lambda r: r.receipt.currency != "USD",
    "REG-01": lambda r: r.receipt.entity == "APAC" and "alcohol" in _categories(r),
    "REG-02": lambda r: r.receipt.entity == "APAC" and _meal_type(r),
    "REG-03": lambda r: r.receipt.entity == "EMEA" and _meal_type(r),
    "REG-04": _entity("EMEA"),
    "EXC-03": _always,
}


def retrieve(receipt: ClassifiedReceipt) -> RuleSet:
    return RuleSet(rule_ids=tuple(sorted(rid for rid, hit in TRIGGERS.items() if hit(receipt))))
