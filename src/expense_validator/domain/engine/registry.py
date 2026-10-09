"""The 37 in-scope rules: document, effect, scope, decisions followed, and verbatim evidence.

Every `evidence` sentence is copied from its policy document; a test checks it is verbatim
(EXC-04, research R8). TIME-01 to TIME-04 are out of scope and absent on purpose.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from expense_validator.domain.models import Severity

Kind = Literal["exception", "review_signal", "modifier"]
Scope = Literal["items", "receipt", "none"]

MEALS = "meals-and-entertainment-policy.md"
TECH = "technology-and-equipment-policy.md"
GIFTS = "gifts-and-awards-policy.md"
NONREIMB = "non-reimbursable-items.md"
MCC = "merchant-category-risk.md"
DOCS = "receipt-documentation-requirements.md"
REGIONAL = "regional-addendum.md"
APPROVAL = "approval-and-exception-handling.md"


@dataclass(frozen=True)
class RuleSpec:
    rule_id: str
    policy_doc: str
    kind: Kind
    severity: Severity | None
    scope: Scope
    decisions: tuple[str, ...]
    evidence: str
    evidence_variants: dict[str, str] = field(default_factory=dict)


def _exc(
    rule_id: str,
    doc: str,
    severity: Severity,
    scope: Scope,
    evidence: str,
    decisions: tuple[str, ...] = (),
    variants: dict[str, str] | None = None,
) -> RuleSpec:
    return RuleSpec(rule_id, doc, "exception", severity, scope, decisions, evidence, variants or {})


_RULES = [
    # meals-and-entertainment-policy.md
    _exc(
        "MEAL-01",
        MEALS,
        "medium",
        "receipt",
        "Meal spend is capped at $75 per person per day for domestic travel and $100 per person "
        "per day for international travel.",
        ("A8",),
    ),
    _exc(
        "MEAL-02",
        MEALS,
        "low",
        "receipt",
        "Any meal receipt (as defined in MEAL-01) whose receipt total is above $150 in USD must "
        "record the number of attendees.",
    ),
    _exc(
        "ALC-01",
        MEALS,
        "high",
        "items",
        "Alcohol is reimbursable only on a receipt declared as Client Entertainment that records "
        "an attendee count of two or more.",
    ),
    _exc(
        "ALC-02",
        MEALS,
        "medium",
        "items",
        "Where alcohol is permitted under ALC-01, it is capped at $30 per attendee: the USD total "
        "of the alcohol lines, divided by the attendee count.",
    ),
    _exc(
        "ALC-03",
        MEALS,
        "high",
        "items",
        "Alcohol purchased from a package store, liquor store, or any other merchant that is not "
        "a restaurant, bar or hotel is never reimbursable, regardless of business context.",
    ),
    _exc(
        "ENT-01",
        MEALS,
        "medium",
        "items",
        "Golf, sporting events, theatre, concerts, and similar venue spend requires prior VP "
        "approval, recorded as an approval reference (see EXC-02).",
        ("A5", "A6"),
    ),
    _exc(
        "ENT-02",
        MEALS,
        "high",
        "items",
        "Gambling spend of any kind is prohibited and is a high exception.",
    ),
    # technology-and-equipment-policy.md
    _exc(
        "TECH-01",
        TECH,
        "high",
        "items",
        "Purchase of any of these on an expense report is a high exception, regardless of stated "
        "business purpose.",
    ),
    _exc(
        "TECH-02",
        TECH,
        "medium",
        "items",
        "Any accessory or peripheral above $200 requires a pre-approval reference (see EXC-02); "
        "without one it is a medium exception.",
        ("A5",),
    ),
    _exc(
        "TECH-03",
        TECH,
        "high",
        "items",
        "Mobile phone hardware is procured centrally by IT and is never reimbursable on an "
        "expense report.",
        ("A6",),
    ),
    _exc(
        "TECH-04",
        TECH,
        "low",
        "items",
        "Any software or SaaS subscription on an expense report requires a manager approval "
        "reference (see EXC-02).",
        ("A5",),
    ),
    # gifts-and-awards-policy.md
    _exc(
        "GIFT-01",
        GIFTS,
        "medium",
        "items",
        "Gifts to clients and prospects are capped at $50 per recipient per occasion.",
        ("A7", "A9"),
        {
            "unnamed": "Any gift of $10 or more must also name its recipient, in the line "
            "description or elsewhere on the expense; an unnamed gift at that value is a medium "
            "exception."
        },
    ),
    _exc(
        "GIFT-02",
        GIFTS,
        "high",
        "items",
        "Gift cards, prepaid cards, vouchers, and any other cash equivalent are never "
        "reimbursable, at any amount and for any recipient.",
    ),
    _exc(
        "GIFT-03",
        GIFTS,
        "medium",
        "items",
        "Recognition gifts for employees must be processed through HR and are not reimbursable "
        "on an expense report.",
        ("A9",),
    ),
    _exc(
        "GIFT-04",
        GIFTS,
        "critical",
        "items",
        "Gifts, meals, or anything of value provided to a government official, public employee, "
        "or state-owned enterprise employee are prohibited under our anti-corruption policy, at "
        "any amount.",
        ("A9",),
    ),
    # non-reimbursable-items.md
    _exc(
        "PERS-01",
        NONREIMB,
        "medium",
        "items",
        "Toiletries, cosmetics, razors, haircuts, salon services, spa treatments, and massage are "
        "not reimbursable.",
        ("A5",),
    ),
    _exc(
        "PERS-02",
        NONREIMB,
        "medium",
        "items",
        "Clothing, footwear, and fashion accessories such as belts, ties and bags are not "
        "reimbursable; a medium exception.",
        ("A5",),
    ),
    _exc(
        "PERS-03",
        NONREIMB,
        "high",
        "items",
        "Cigarettes, cigars, loose tobacco, vaping devices and e-liquids are not reimbursable.",
    ),
    _exc(
        "HOUSE-01",
        NONREIMB,
        "medium",
        "items",
        "Cleaning supplies, laundry products, household paper goods (paper towels, toilet paper, "
        "tissues), kitchenware and drinkware, bedding, furniture, small appliances, and home "
        "décor are not reimbursable, whether bought for home or for an office — office stock of "
        "this kind is bought centrally.",
    ),
    _exc(
        "HEALTH-01",
        NONREIMB,
        "low",
        "items",
        "OTC medication is reimbursable only on a receipt linked to a trip, up to $25 in total "
        "across all of that trip's receipts.",
        ("A4", "A6"),
        {
            "prescription": "Prescription medication is never reimbursable on an expense report "
            "and is a medium exception."
        },
    ),
    _exc(
        "LAUNDRY-01",
        NONREIMB,
        "low",
        "items",
        "Reimbursable only on trips of four or more nights, using the trip length on the receipt.",
    ),
    # merchant-category-risk.md
    _exc(
        "MCC-01",
        MCC,
        "high",
        "receipt",
        "A transaction at a high-risk MCC raises a high exception on its own, whatever the line "
        "items say.",
    ),
    RuleSpec(
        "MCC-02",
        MCC,
        "review_signal",
        None,
        "receipt",
        (),
        "A medium-risk MCC raises a review signal only.",
    ),
    RuleSpec(
        "MCC-03",
        MCC,
        "modifier",
        None,
        "none",
        (),
        "A bar (MCC 5813) serves alcohol on the premises, so ALC-01 and ALC-02 apply to it "
        "exactly as they do to a restaurant, and it is never treated as retail under ALC-03.",
    ),
    # receipt-documentation-requirements.md
    _exc(
        "DOC-01",
        DOCS,
        "medium",
        "receipt",
        "Any receipt with a total above $75 (in USD) must be itemized.",
    ),
    _exc(
        "DOC-02",
        DOCS,
        "medium",
        "receipt",
        "A receipt must show the merchant name, the transaction date, and the total.",
    ),
    _exc(
        "DOC-03",
        DOCS,
        "medium",
        "receipt",
        "A receipt is misclassified when none of its line items belongs to a category that its "
        "declared expense type covers.",
        ("A7",),
    ),
    _exc(
        "DOC-04",
        DOCS,
        "medium",
        "receipt",
        "Receipts in a currency other than USD must record the transaction currency and the "
        "conversion rate used; a receipt missing either is a medium exception.",
        ("A1",),
    ),
    # regional-addendum.md
    _exc(
        "REG-01",
        REGIONAL,
        "high",
        "items",
        "Alcohol is never reimbursable for APAC-entity employees, including within client "
        "entertainment.",
    ),
    _exc(
        "REG-02",
        REGIONAL,
        "medium",
        "receipt",
        "The APAC daily meal cap is $60 per person, replacing both MEAL-01 figures for APAC "
        "employees.",
    ),
    _exc(
        "REG-03",
        REGIONAL,
        "medium",
        "receipt",
        "The EMEA daily meal cap is EUR 70 per person, replacing both MEAL-01 figures for EMEA "
        "employees.",
        ("A1",),
    ),
    _exc(
        "REG-04",
        REGIONAL,
        "low",
        "receipt",
        "Receipts above EUR 50 — converted at the euro rate on the transaction date for a receipt "
        "in another currency — must be valid VAT receipts showing the merchant VAT number.",
        ("A1", "A2"),
    ),
    RuleSpec(
        "REG-05",
        REGIONAL,
        "modifier",
        None,
        "none",
        ("A1",),
        "Currency conversion uses the rate on the transaction date, which must be recorded on the "
        "expense record.",
    ),
    # approval-and-exception-handling.md
    RuleSpec(
        "EXC-01",
        APPROVAL,
        "modifier",
        None,
        "none",
        (),
        "A receipt's disposition is determined by the most severe exception raised against it:",
    ),
    RuleSpec(
        "EXC-02",
        APPROVAL,
        "modifier",
        None,
        "none",
        ("A5",),
        "Where a rule requires such a reference, a recorded one satisfies that rule and no "
        "exception is raised — provided it is the kind the rule asks for",
    ),
    RuleSpec(
        "EXC-03",
        APPROVAL,
        "review_signal",
        None,
        "items",
        ("A3",),
        "Where the category of an item cannot be determined with sufficient confidence, raise a "
        "review signal with rule ID `EXC-03` rather than an exception, and leave that item out "
        "of every other rule's calculation for the receipt.",
    ),
    RuleSpec(
        "EXC-04",
        APPROVAL,
        "modifier",
        None,
        "none",
        (),
        "Every exception must cite the rule identifier, the policy document it comes from, and "
        "the line items it concerns.",
    ),
]

REGISTRY: dict[str, RuleSpec] = {spec.rule_id: spec for spec in _RULES}
