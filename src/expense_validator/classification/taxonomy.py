"""The 21-category taxonomy, parsed from data/category-taxonomy.md and used as given.

The restricted flag always comes from this table, never from a model answer.
"""

from __future__ import annotations

import re
from typing import Literal

from expense_validator.paths import TAXONOMY_FILE

Category = Literal[
    "alcohol",
    "tobacco",
    "personal_electronics",
    "gift",
    "gift_card",
    "household_goods",
    "personal_care",
    "clothing",
    "gambling",
    "jewelry",
    "food_beverage",
    "computer_accessory",
    "office_supplies",
    "lodging",
    "ground_transport",
    "airfare",
    "laundry_service",
    "health_otc",
    "software_subscription",
    "service_fee",
    "other",
]

_ROW = re.compile(r"^\| `([a-z_]+)` \| (yes|no) \| ([^|]+) \|", re.M)


def _parse() -> tuple[dict[str, bool], dict[str, str]]:
    text = TAXONOMY_FILE.read_text(encoding="utf-8")
    restricted: dict[str, bool] = {}
    examples: dict[str, str] = {}
    for name, flag, example in _ROW.findall(text):
        restricted[name] = flag == "yes"
        examples[name] = example.strip()
    return restricted, examples


_RESTRICTED, EXAMPLES = _parse()
CATEGORIES: tuple[str, ...] = tuple(_RESTRICTED)


def restricted_for(category: str) -> bool:
    """Return the taxonomy's restricted flag for a category."""
    return _RESTRICTED[category]
