"""EXC-01, implemented exactly (T029, FR-016)."""

import itertools

import pytest

from expense_validator.engine.disposition import disposition


@pytest.mark.parametrize("severity", ["critical", "high", "medium"])
def test_any_serious_exception_flags(severity: str) -> None:
    assert disposition([severity], has_signals=False) == "flag"
    assert disposition(["low", severity], has_signals=True) == "flag"


def test_only_low_exceptions_review() -> None:
    assert disposition(["low"], has_signals=False) == "review"
    assert disposition(["low", "low"], has_signals=True) == "review"


def test_only_signals_review() -> None:
    assert disposition([], has_signals=True) == "review"


def test_nothing_passes() -> None:
    assert disposition([], has_signals=False) == "pass"


def test_order_does_not_matter() -> None:
    severities = ["low", "medium", "low", "critical"]
    results = {disposition(list(p), has_signals=False) for p in itertools.permutations(severities)}
    assert results == {"flag"}
