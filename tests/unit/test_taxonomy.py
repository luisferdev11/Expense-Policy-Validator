"""The taxonomy is parsed from data/category-taxonomy.md and used as given (T011)."""

import re
from typing import get_args

from expense_validator.classification import taxonomy
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
    assert all(taxonomy.EXAMPLES[c] for c in taxonomy.CATEGORIES)
