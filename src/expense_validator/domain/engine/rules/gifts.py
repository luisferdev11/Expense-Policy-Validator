"""gifts-and-awards-policy.md: GIFT-01 to GIFT-04 (A7 gift definition, A9 recipient fields).

- Food, drink and gratuities consumed at a meal are not gifts under GIFT-01, even when a guest
  is named.
- Gift cards and cash equivalents fall under GIFT-02 alone.
- GIFT-04 replaces GIFT-01 for the lines provided to an official, including a meal line but not
  a gratuity. Employee recognition gifts are GIFT-03, not client gifts under GIFT-01.
"""

from __future__ import annotations

from decimal import Decimal

from expense_validator.domain.engine.base import Hit, Line, Rule, RuleInput, line_ids, money

GIFT_CAP_USD = Decimal("50")
NAMED_THRESHOLD_USD = Decimal("10")
MEAL_CATEGORIES = frozenset({"food_beverage", "alcohol", "service_fee"})
NOT_CLIENT_GIFTS = frozenset({"employee", "government_official"})


def _client_gift_lines(inp: RuleInput) -> list[Line]:
    declared = inp.receipt.submitted_expense_type == "Client Gifts"
    return [
        line
        for line in inp.lines
        if line.category not in MEAL_CATEGORIES
        and line.category != "gift_card"
        and line.recipient_kind not in NOT_CLIENT_GIFTS
        and (declared or line.recipient_name)
    ]


def gift_01(inp: RuleInput) -> list[Hit]:
    candidates = _client_gift_lines(inp)
    groups: dict[str, list[Line]] = {}
    for line in candidates:
        if line.recipient_name:
            groups.setdefault(line.recipient_name.casefold(), []).append(line)
    over_cap = [
        line
        for group in groups.values()
        if sum((line.amount_usd for line in group), Decimal("0")) > GIFT_CAP_USD
        for line in group
    ]
    unnamed = [
        line
        for line in candidates
        if not line.recipient_name and line.amount_usd >= NAMED_THRESHOLD_USD
    ]
    if not over_cap and not unnamed:
        return []
    computed = {"cap_per_recipient_usd": money(GIFT_CAP_USD)}
    if unnamed:
        computed["unnamed_gifts_at_or_above_usd"] = money(NAMED_THRESHOLD_USD)
    variant = "unnamed" if unnamed and not over_cap else "default"
    return [Hit("GIFT-01", line_ids([*over_cap, *unnamed]), computed, variant=variant)]


def gift_02(inp: RuleInput) -> list[Hit]:
    lines = inp.of("gift_card")
    return [Hit("GIFT-02", line_ids(lines))] if lines else []


def gift_03(inp: RuleInput) -> list[Hit]:
    lines = [
        line
        for line in inp.lines
        if line.recipient_kind == "employee"
        and line.category not in MEAL_CATEGORIES
        and line.category != "gift_card"
    ]
    return [Hit("GIFT-03", line_ids(lines))] if lines else []


def gift_04(inp: RuleInput) -> list[Hit]:
    lines = [
        line
        for line in inp.lines
        if line.recipient_kind == "government_official" and line.category != "service_fee"
    ]
    return [Hit("GIFT-04", line_ids(lines))] if lines else []


RULES: dict[str, Rule] = {
    "GIFT-01": gift_01,
    "GIFT-02": gift_02,
    "GIFT-03": gift_03,
    "GIFT-04": gift_04,
}
