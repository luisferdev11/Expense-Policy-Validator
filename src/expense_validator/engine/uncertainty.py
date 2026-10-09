"""EXC-03: uncertain items raise a review signal and leave every other calculation (A3).

An item is uncertain when the classifier could not classify it, or its confidence is below the
single named threshold (`exc03.threshold`, provisional 0.5 in iteration 1). A non-itemized
charge is `other` by definition and never uncertain.
"""

from __future__ import annotations

from decimal import Decimal

from expense_validator.engine import fx
from expense_validator.engine.base import Hit, Line, RuleInput
from expense_validator.engine.settings import Settings
from expense_validator.models import ClassifiedReceipt, ReceiptInput


def _usd(value: Decimal, recorded_usd: Decimal, amount: Decimal, receipt: ReceiptInput) -> Decimal:
    """Convert with the receipt's rate (A1). With no rate recorded (a DOC-04 exception),
    fall back to the record's own USD conversion of the line, scaled for unit prices."""
    converted = fx.to_usd(value, receipt)
    if converted is not None:
        return converted
    return recorded_usd if amount == 0 else recorded_usd * value / amount


def split_lines(
    classified: ClassifiedReceipt, settings: Settings
) -> tuple[tuple[Line, ...], tuple[str, ...]]:
    """Certain lines for the rules, and the IDs of the uncertain ones."""
    receipt = classified.receipt
    lines: list[Line] = []
    uncertain: list[str] = []
    for position, (item, c) in enumerate(
        zip(receipt.line_items, classified.classifications, strict=True)
    ):
        if not receipt.itemized:
            category = "other"
        elif (
            c.status != "classified"
            or c.category is None
            or Decimal(str(c.confidence)) < settings.exc03_threshold
        ):
            uncertain.append(item.line_id)
            continue
        else:
            category = c.category
        lines.append(
            Line(
                line_id=item.line_id,
                category=category,
                subtype=c.subtype if c.category == "other" else "none",
                recipient_kind=c.recipient_kind,
                recipient_name=c.recipient_name,
                amount_usd=_usd(item.amount, item.amount_usd, item.amount, receipt),
                unit_price_usd=_usd(item.unit_price, item.amount_usd, item.amount, receipt),
                position=position,
            )
        )
    return tuple(lines), tuple(uncertain)


def exc_03(inp: RuleInput) -> list[Hit]:
    if not inp.uncertain_line_ids:
        return []
    return [Hit("EXC-03", inp.uncertain_line_ids, {"threshold": str(inp.settings.exc03_threshold)})]
