"""Prompt cls-v2 and its strict output schema (research R4, contracts/classifier-output-cls-v2).

Ported from explorations/lib/classifier_prompt.py (cls-v1): the taxonomy-derived system prompt
and its "names lie" rules, extended with the closed subtype for `other` (A6) and the recipient
fields (A9). The model sees only the cleaned description, the merchant name and the MCC.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, cast

from expense_validator.classification.taxonomy import CATEGORIES, EXAMPLES, Category
from expense_validator.models import ClassifierRequest, RecipientKind, Subtype
from expense_validator.normaliser import clean

PROMPT_VERSION = "cls-v2"
PROMPT_NAME = "classify-item-chat"

SUBTYPES: tuple[str, ...] = ("event_ticket", "mobile_handset", "prescription_medication", "none")
RECIPIENT_KINDS: tuple[str, ...] = (
    "none",
    "client_or_prospect",
    "employee",
    "government_official",
)

SYSTEM = (
    "You classify one line item from an expense receipt into exactly one category.\n"
    "Categories (name: typical examples):\n"
    + "\n".join(f"- {c}: {EXAMPLES[c]}" for c in CATEGORIES)
    + "\n\nRules:\n"
    "- Classify what the item IS, not the words in its name. Food cooked with alcohol "
    "(beer-battered fish, rum cake, wine sauce) is food_beverage. Non-alcoholic drinks and "
    "mocktails are food_beverage. Cooking wine is alcohol. Barware and drinkware are "
    "household_goods.\n"
    "- Accessories made for a personal device (cases, chargers) are personal_electronics. "
    "Non-electronic watches are jewelry.\n"
    "- Mobile phones, prescription medication and event tickets have no category: use other.\n"
    "- A non-itemized charge with unknown contents is other.\n"
    "- The item text may be in English, Spanish, French, German, Portuguese or Japanese.\n"
    "- confidence is your probability (0 to 1) that the category is correct.\n"
    "- subtype is used only when category is other: event_ticket (a ticket or entry to golf, a "
    "sporting event, theatre, a concert or a similar venue), mobile_handset (mobile phone "
    "hardware), prescription_medication (medication dispensed on prescription). In every other "
    "case subtype is none.\n"
    "- recipient_kind and recipient_name describe whom the line itself says the item is for. "
    "Read only the line text. government_official: a government official, public employee or "
    "employee of a state-owned enterprise. employee: a colleague or staff member of the "
    "expense-filing company. client_or_prospect: a named client, customer or prospect, or a "
    "named person or organisation the item is given to who is none of the above. none: the "
    "line names nobody. recipient_name is the person or organisation the line names as "
    "recipient, or null.\n"
    "Answer only with JSON: "
    '{"category": <one category>, "confidence": <number>, "subtype": <subtype>, '
    '"recipient_kind": <kind>, "recipient_name": <string or null>}.'
)

SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "category": {"type": "string", "enum": list(CATEGORIES)},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "subtype": {
            "type": "string",
            "enum": list(SUBTYPES),
            "description": "Must be none unless category is other.",
        },
        "recipient_kind": {"type": "string", "enum": list(RECIPIENT_KINDS)},
        "recipient_name": {
            "type": ["string", "null"],
            "description": (
                "The name the line gives for whom the item is for, normalised; null if none."
            ),
        },
    },
    "required": ["category", "confidence", "subtype", "recipient_kind", "recipient_name"],
    "additionalProperties": False,
}

RESPONSE_FORMAT_STRICT: dict[str, Any] = {
    "type": "json_schema",
    "json_schema": {"name": "item_classification", "strict": True, "schema": SCHEMA},
}


class ParseError(ValueError):
    """The answer does not match the cls-v2 schema exactly (reason: schema_violation)."""


@dataclass(frozen=True)
class ParsedAnswer:
    category: Category
    confidence: float
    subtype: Subtype
    recipient_kind: RecipientKind
    recipient_name: str | None


def user_message(request: ClassifierRequest) -> str:
    return (
        f"Item: {request.description_clean}\nMerchant: {request.merchant_name}\nMCC: {request.mcc}"
    )


def messages(request: ClassifierRequest) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": user_message(request)},
    ]


def parse(content: str | None) -> ParsedAnswer:
    """Strict parse: the whole content is one JSON object matching SCHEMA exactly."""
    try:
        obj = json.loads(content or "")
    except json.JSONDecodeError as exc:
        raise ParseError(f"invalid JSON: {exc.msg}") from None
    if not isinstance(obj, dict) or set(obj) != set(SCHEMA["required"]):
        raise ParseError("keys do not match the schema")
    category, confidence = obj["category"], obj["confidence"]
    subtype, kind, name = obj["subtype"], obj["recipient_kind"], obj["recipient_name"]
    if category not in CATEGORIES:
        raise ParseError(f"category not in taxonomy: {category!r}")
    if isinstance(confidence, bool) or not isinstance(confidence, int | float):
        raise ParseError("confidence is not a number")
    if not 0 <= confidence <= 1:
        raise ParseError("confidence outside [0, 1]")
    if subtype not in SUBTYPES or (subtype != "none" and category != "other"):
        raise ParseError(f"invalid subtype {subtype!r} for category {category!r}")
    if kind not in RECIPIENT_KINDS:
        raise ParseError(f"invalid recipient_kind {kind!r}")
    if name is not None and not isinstance(name, str):
        raise ParseError("recipient_name is not a string or null")
    cleaned = clean(name) if name else None
    return ParsedAnswer(
        category=cast(Category, category),
        confidence=float(confidence),
        subtype=cast(Subtype, subtype),
        recipient_kind=cast(RecipientKind, kind),
        recipient_name=cleaned or None,
    )
