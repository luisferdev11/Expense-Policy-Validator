"""Deterministic cleanup, no translation (T019, FR-004)."""

from expense_validator.domain.normaliser import clean, normalise
from tests.factories import item, receipt


def test_nfkc_and_whitespace() -> None:
    # Full-width letters on purpose: NFKC must fold them to ASCII.
    assert clean("  Ｃｏｆｆｅｅ\t\n large  ") == "Coffee large"  # noqa: RUF001


def test_japanese_and_accents_survive() -> None:
    assert clean("懐石コース　4名") == "懐石コース 4名"
    assert clean("Café  crème") == "Café crème"


def test_case_is_kept() -> None:
    assert clean("USB-C Dock") == "USB-C Dock"


def test_normalise_keeps_raw_and_language() -> None:
    r = receipt([item(1, description="  Bière   pression ", language="fr")])
    (out,) = normalise(r)
    assert out.description_raw == "  Bière   pression "
    assert out.description_clean == "Bière pression"
    assert out.language == "fr"
    assert out.line_id == "SYN-1-L1"


def test_same_input_same_output() -> None:
    r = receipt([item(1, description="Taxi  airport"), item(2, description="Tip")])
    assert normalise(r) == normalise(r)
