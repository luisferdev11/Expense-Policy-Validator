"""EXC-01: disposition is computed, not judged (FR-016)."""

from __future__ import annotations

from collections.abc import Iterable

from expense_validator.domain.models import Disposition


def disposition(severities: Iterable[str], has_signals: bool) -> Disposition:
    """Any critical, high or medium exception flags; any low exception or signal reviews."""
    seen = set(severities)
    if seen & {"critical", "high", "medium"}:
        return "flag"
    if "low" in seen or has_signals:
        return "review"
    return "pass"
