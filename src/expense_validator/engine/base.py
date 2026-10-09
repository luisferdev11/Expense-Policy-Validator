"""Shared engine types: the per-receipt rule input and the raw rule hit. Pure, no I/O."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

from expense_validator.engine.settings import Settings
from expense_validator.models import (
    CrossReceiptContext,
    ReceiptInput,
    RecipientKind,
    Severity,
    Subtype,
)

CENT = Decimal("0.01")
SEVERITY_ORDER: dict[str, int] = {"low": 1, "medium": 2, "high": 3, "critical": 4}


def line_ids(lines: Iterable[Line]) -> tuple[str, ...]:
    return tuple(line.line_id for line in lines)


def money(value: Decimal) -> str:
    """Render a USD or EUR amount with two decimals, for `computed` and explanations."""
    return str(value.quantize(CENT, rounding=ROUND_HALF_UP))


@dataclass(frozen=True)
class Line:
    """A classified line the rules may use. Uncertain lines never become a `Line` (EXC-03)."""

    line_id: str
    category: str
    subtype: Subtype
    recipient_kind: RecipientKind
    recipient_name: str | None
    amount_usd: Decimal
    unit_price_usd: Decimal
    position: int


@dataclass(frozen=True)
class RuleInput:
    receipt: ReceiptInput
    lines: tuple[Line, ...]
    uncertain_line_ids: tuple[str, ...]
    context: CrossReceiptContext
    settings: Settings

    def of(self, *categories: str) -> tuple[Line, ...]:
        return tuple(line for line in self.lines if line.category in categories)

    def reference_kind(self) -> str | None:
        """The kind of the recorded approval reference, from the prefix table (A5)."""
        ref = self.receipt.pre_approval_ref
        if not ref:
            return None
        for prefix, kind in self.settings.reference_prefixes.items():
            if ref.startswith(prefix):
                return kind
        return "unknown"


@dataclass(frozen=True)
class Hit:
    """One rule firing on one receipt, before merging and before evidence is attached."""

    rule_id: str
    line_ids: tuple[str, ...] = ()
    computed: dict[str, str] = field(default_factory=dict)
    severity: Severity | None = None
    variant: str = "default"
    # True when the rule could not be evaluated (a euro rate missing, A1): the receipt gets a
    # review signal under this rule ID instead of an exception, so it never passes.
    as_signal: bool = False


Rule = Callable[[RuleInput], list[Hit]]
