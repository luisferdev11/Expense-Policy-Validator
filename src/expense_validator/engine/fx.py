"""FX component, decision A1. All policy thresholds are evaluated on USD amounts (DOC-04).

Defaults follow the policy text: the rate recorded on the receipt, as of the transaction date
(REG-05). A euro rate for EUR thresholds is the receipt's own rate on a euro receipt; otherwise
it comes from the versioned table in config/eur_rates.csv. A missing rate returns None and the
calling rule sends the receipt to review, never to pass (fx.missing_rate_disposition).
The other A1 settings (billing date, mid/high/low rates) are open question Q1 and are refused
until a rate source is approved.
"""

from __future__ import annotations

from decimal import Decimal

from expense_validator.engine.settings import Settings
from expense_validator.models import ReceiptInput

SUPPORTED_DATE_BASIS = ("transaction",)
SUPPORTED_RATE_KIND = ("recorded",)


def check_supported(settings: Settings) -> None:
    if settings.fx_date_basis not in SUPPORTED_DATE_BASIS:
        raise ValueError(f"fx.date_basis {settings.fx_date_basis!r} has no rate source yet (Q1)")
    if settings.fx_rate_kind not in SUPPORTED_RATE_KIND:
        raise ValueError(f"fx.rate_kind {settings.fx_rate_kind!r} has no rate source yet (Q1)")


def usd_rate(receipt: ReceiptInput) -> Decimal | None:
    """The receipt's recorded rate to USD; 1 for a USD receipt with no rate recorded."""
    if receipt.fx_rate_to_usd is not None:
        return receipt.fx_rate_to_usd
    if receipt.currency == "USD":
        return Decimal("1")
    return None


def to_usd(amount: Decimal, receipt: ReceiptInput) -> Decimal | None:
    rate = usd_rate(receipt)
    return None if rate is None else amount * rate


def eur_to_usd(receipt: ReceiptInput, settings: Settings) -> Decimal | None:
    """USD value of one euro on the transaction date (REG-03, REG-04)."""
    if receipt.currency == "EUR" and receipt.fx_rate_to_usd is not None:
        return receipt.fx_rate_to_usd
    if receipt.transaction_datetime is None:
        return None
    return settings.eur_to_usd.get(receipt.transaction_datetime.date())


def eur_threshold_usd(eur: Decimal, receipt: ReceiptInput, settings: Settings) -> Decimal | None:
    rate = eur_to_usd(receipt, settings)
    return None if rate is None else eur * rate
