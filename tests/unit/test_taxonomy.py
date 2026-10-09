"""The static taxonomy table equals data/category-taxonomy.md, used as given (T011, ADR 0003)."""

import re
from typing import get_args

from expense_validator.domain import taxonomy
from expense_validator.paths import TAXONOMY_FILE


def _table() -> dict[str, bool]:
    text = TAXONOMY_FILE.read_text(encoding="utf-8")
    rows = re.findall(r"^\| `([a-z_]+)` \| (yes|no) \|", text, re.M)
    return {name: flag == "yes" for name, flag in rows}


def test_exactly_21_categories() -> None:
    assert len(taxonomy.CATEGORIES) == 21


def test_restricted_flags_match_the_file() -> None:
    assert {c: taxonomy.restricted_for(c) for c in taxonomy.CATEGORIES} == _table()


def test_static_literal_matches_the_file() -> None:
    assert set(get_args(taxonomy.Category)) == set(_table())


def test_examples_are_available_for_the_prompt() -> None:
    from expense_validator.adapters.openrouter.prompt import EXAMPLES

    assert all(EXAMPLES[c] for c in taxonomy.CATEGORIES)
