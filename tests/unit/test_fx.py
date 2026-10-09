"""FX component, decision A1 (T046, FR-013)."""

from dataclasses import replace
from datetime import date
from decimal import Decimal as D

import pytest

from expense_validator.engine import fx
from expense_validator.engine.settings import load_settings
from tests.factories import item, receipt

S = load_settings()


def test_usd_amounts_are_unchanged() -> None:
    r = receipt([item(1, amount="12.34")])
    assert fx.to_usd(D("12.34"), r) == D("12.34")


def test_foreign_amounts_use_the_recorded_rate() -> None:
    r = receipt([item(1, amount="1000", fx="0.012")], currency="INR", fx_rate_to_usd=D("0.012"))
    assert fx.to_usd(D("1000"), r) == D("12.000")


def test_missing_rate_on_a_foreign_receipt_gives_none() -> None:
    r = receipt([item(1, amount="10")], currency="EUR", fx_rate_to_usd=None)
    assert fx.to_usd(D("10"), r) is None


def test_eur_receipt_uses_its_own_rate_for_eur_thresholds() -> None:
    r = receipt([item(1, amount="70", fx="1.08")], currency="EUR", fx_rate_to_usd=D("1.08"))
    assert fx.eur_to_usd(r, S) == D("1.08")
    assert fx.eur_threshold_usd(D("70"), r, S) == D("75.60")


def test_non_eur_receipt_without_a_table_rate_gives_none() -> None:
    r = receipt([item(1, amount="50", fx="1.27")], currency="GBP", fx_rate_to_usd=D("1.27"))
    assert fx.eur_to_usd(r, S) is None


def test_non_eur_receipt_uses_the_table_by_transaction_date() -> None:
    table = replace(S, eur_to_usd={date(2026, 5, 1): D("1.10")})
    r = receipt([item(1, amount="50", fx="1.27")], currency="GBP", fx_rate_to_usd=D("1.27"))
    assert fx.eur_to_usd(r, table) == D("1.10")


def test_defaults_follow_a1_and_other_settings_are_refused() -> None:
    assert (S.fx_date_basis, S.fx_rate_kind) == ("transaction", "recorded")
    with pytest.raises(ValueError):
        fx.check_supported(replace(S, fx_date_basis="billing"))
    with pytest.raises(ValueError):
        fx.check_supported(replace(S, fx_rate_kind="mid"))
