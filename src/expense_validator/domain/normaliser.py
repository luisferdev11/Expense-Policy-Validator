"""Normaliser: deterministic text cleanup, no translation (FR-004).

The classifier reads the original language; whether a translation step helps is experiment E5
in iteration 2. Case is kept: matching code case-folds on its own side.
"""

from __future__ import annotations

import re
import unicodedata

from expense_validator.domain.models import NormalisedItem, ReceiptInput

_WHITESPACE = re.compile(r"\s+")


def clean(text: str) -> str:
    """Unicode NFKC, whitespace collapsed to single spaces, trimmed."""
    return _WHITESPACE.sub(" ", unicodedata.normalize("NFKC", text)).strip()


def normalise(receipt: ReceiptInput) -> tuple[NormalisedItem, ...]:
    return tuple(
        NormalisedItem(
            line_id=item.line_id,
            description_raw=item.description_raw,
            description_clean=clean(item.description_raw),
            language=item.language,
        )
        for item in receipt.line_items
    )
