"""Versioned classification prompt and strict JSON schema shared by packages 5 and 6.

The prompt is built from data/category-taxonomy.md at import time (categories, restricted flag
and typical examples) plus the taxonomy's own "names lie" guidance. The model sees only the item
description, the merchant name and the MCC: never the declared expense type or attendee count.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

EXP = Path(__file__).resolve().parent.parent  # explorations/
REPO = EXP.parent
PROMPT_VERSION = "cls-v1"

_tax = (REPO / "data" / "category-taxonomy.md").read_text()
TAXONOMY: dict[str, tuple[bool, str]] = {
    c: (r == "yes", ex.strip())
    for c, r, ex in re.findall(r"^\| `([a-z_]+)` \| (yes|no) \| ([^|]+) \|", _tax, re.M)
}
CATEGORIES = list(TAXONOMY)

SYSTEM = (
    "You classify one line item from an expense receipt into exactly one category.\n"
    "Categories (name: typical examples):\n"
    + "\n".join(f"- {c}: {ex}" for c, (_, ex) in TAXONOMY.items())
    + "\n\nRules:\n"
    "- Classify what the item IS, not the words in its name. Food cooked with alcohol "
    "(beer-battered fish, rum cake, wine sauce) is food_beverage. Non-alcoholic drinks and "
    "mocktails are food_beverage. Cooking wine is alcohol. Barware and drinkware are household_goods.\n"
    "- Accessories made for a personal device (cases, chargers) are personal_electronics. "
    "Non-electronic watches are jewelry.\n"
    "- Mobile phones, prescription medication and event tickets have no category: use other.\n"
    "- A non-itemized charge with unknown contents is other.\n"
    "- The item text may be in English, Spanish, French, German, Portuguese or Japanese.\n"
    "- confidence is your probability (0 to 1) that the category is correct.\n"
    'Answer only with JSON: {"category": <one category>, "confidence": <number>}.'
)

SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "category": {"type": "string", "enum": CATEGORIES},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
    },
    "required": ["category", "confidence"],
    "additionalProperties": False,
}

RESPONSE_FORMAT_STRICT: dict[str, Any] = {
    "type": "json_schema",
    "json_schema": {"name": "item_category", "strict": True, "schema": SCHEMA},
}


def user_message(description: str, merchant_name: str, mcc: int | str) -> str:
    return f"Item: {description}\nMerchant: {merchant_name}\nMCC: {mcc}"


def messages(item: dict[str, Any]) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": SYSTEM},
        {
            "role": "user",
            "content": user_message(item["description"], item["merchant_name"], item["mcc"]),
        },
    ]


def cache_input(item: dict[str, Any]) -> str:
    return user_message(item["description"], item["merchant_name"], item["mcc"])


def parse(content: str | None) -> tuple[str | None, float | None, str | None]:
    """Return (category, confidence, error). Tolerates code fences and surrounding text."""
    if not content:
        return None, None, "empty content"
    text = content.strip()
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return None, None, "no JSON object"
    try:
        obj = json.loads(m.group(0))
    except json.JSONDecodeError as exc:
        return None, None, f"invalid JSON: {exc}"
    cat = obj.get("category")
    if cat not in TAXONOMY:
        return None, None, f"category not in taxonomy: {cat!r}"
    conf = obj.get("confidence")
    return cat, float(conf) if isinstance(conf, (int, float)) else None, None


def schema_valid(content: str | None) -> bool:
    """Strict check: the whole content is a JSON object matching SCHEMA exactly."""
    try:
        obj = json.loads(content or "")
    except json.JSONDecodeError:
        return False
    if not isinstance(obj, dict) or set(obj) != {"category", "confidence"}:
        return False
    conf = obj["confidence"]
    return obj["category"] in TAXONOMY and isinstance(conf, (int, float)) and 0 <= conf <= 1


if __name__ == "__main__":
    print(PROMPT_VERSION, len(CATEGORIES), "categories")
    print(SYSTEM)
