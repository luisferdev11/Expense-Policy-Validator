"""The 21-category taxonomy as a static table, used as given (data/category-taxonomy.md).

Pure: no file is read here. A test keeps this table equal to the data file, so the file stays
the source of truth (ADR 0003). The restricted flag always comes from this table, never from a
model answer.
"""

from __future__ import annotations

from typing import Literal

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

RESTRICTED: dict[str, bool] = {
    "alcohol": True,
    "tobacco": True,
    "personal_electronics": True,
    "gift": True,
    "gift_card": True,
    "household_goods": True,
    "personal_care": True,
    "clothing": True,
    "gambling": True,
    "jewelry": True,
    "food_beverage": False,
    "computer_accessory": False,
    "office_supplies": False,
    "lodging": False,
    "ground_transport": False,
    "airfare": False,
    "laundry_service": False,
    "health_otc": False,
    "software_subscription": False,
    "service_fee": False,
    "other": False,
}
CATEGORIES: tuple[str, ...] = tuple(RESTRICTED)


def restricted_for(category: str) -> bool:
    """Return the taxonomy's restricted flag for a category."""
    return RESTRICTED[category]
