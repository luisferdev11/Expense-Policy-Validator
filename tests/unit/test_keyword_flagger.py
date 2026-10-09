"""keyword-flagger: the legacy kind of system (T081, FR-032)."""

from eval.baselines import flag_receipt, flagged_lines
from tests.factories import item, receipt


def test_any_restricted_word_flags_the_receipt() -> None:
    r = receipt([item(1, description="Grilled salmon"), item(2, description="Glass of wine")])
    assert flag_receipt(r) == "flag"
    assert flagged_lines(r) == {"SYN-1-L2"}


def test_no_restricted_word_passes() -> None:
    r = receipt([item(1, description="Taxi to airport"), item(2, description="Notebook")])
    assert flag_receipt(r) == "pass"


def test_naive_on_purpose() -> None:
    r = receipt([item(1, description="Beer-battered cod")])
    assert flag_receipt(r) == "flag"
