"""Comparing the deciding classifier with a shadow, and the agreement report (spec 007, US2).

Pure: it takes classifications and returns numbers, with no store, no model and no answer labels.
Every figure carries its k and N, and every proportion its Wilson interval (principle VI).
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from expense_validator.domain.models import Classification
from expense_validator.domain.stats import wilson


@dataclass(frozen=True)
class Proportion:
    k: int
    n: int
    rate: float | None
    interval: tuple[float, float] | None


def proportion(k: int, n: int) -> Proportion:
    if n == 0:
        return Proportion(k, n, None, None)
    return Proportion(k, n, k / n, wilson(k, n))


@dataclass(frozen=True)
class LineComparison:
    """One line, as the deciding classifier and the shadow answered it."""

    line_id: str
    primary: Classification
    shadow: Classification
    comparable: bool  # both sides classified it
    agrees_category: bool
    agrees_all: bool  # category, subtype, recipient kind and recipient name


def _name(value: str | None) -> str:
    return (value or "").strip().casefold()


def compare(
    primary: Sequence[Classification], shadow: Sequence[Classification]
) -> list[LineComparison]:
    """Pair the answers by line, in the deciding classifier's order. A line the shadow has no row
    for is left out; a line either side could not classify is kept but is not comparable, and
    counts as agreeing on nothing."""
    by_line = {c.line_id: c for c in shadow}
    out = []
    for p in primary:
        s = by_line.get(p.line_id)
        if s is None:
            continue
        comparable = p.status == "classified" and s.status == "classified"
        same_category = comparable and p.category == s.category
        out.append(
            LineComparison(
                line_id=p.line_id,
                primary=p,
                shadow=s,
                comparable=comparable,
                agrees_category=same_category,
                agrees_all=same_category
                and p.subtype == s.subtype
                and p.recipient_kind == s.recipient_kind
                and _name(p.recipient_name) == _name(s.recipient_name),
            )
        )
    return out


@dataclass(frozen=True)
class Confusion:
    primary: str
    shadow: str
    count: int


@dataclass(frozen=True)
class Corrections:
    """How often each classifier matched the reviewer on the lines a reviewer corrected."""

    corrected_lines: int  # corrected lines among the compared ones
    n: int  # of those, the lines both classifiers answered
    primary: Proportion
    shadow: Proportion


@dataclass(frozen=True)
class AgreementReport:
    receipts: int
    lines: int
    comparable: int
    category: Proportion
    restricted: Proportion
    subtype: Proportion
    recipient_kind: Proportion
    all_fields: Proportion
    shadow_unclassified: dict[str, int]  # the shadow's lines it could not classify, by reason
    confusion: list[Confusion]
    corrections: Corrections


def agreement(
    receipts: Sequence[tuple[str, Sequence[LineComparison]]],
    corrected: Mapping[tuple[str, str], str],
) -> AgreementReport:
    """The report over `(receipt_id, comparisons)` pairs. `corrected` maps `(receipt_id, line_id)`
    to the category a reviewer chose (the latest correction of the line)."""
    everything = [(rid, c) for rid, comparisons in receipts for c in comparisons]
    comparable = [(rid, c) for rid, c in everything if c.comparable]
    n = len(comparable)

    def share(test: str) -> Proportion:
        if test == "category":
            k = sum(1 for _, c in comparable if c.agrees_category)
        elif test == "restricted":
            k = sum(1 for _, c in comparable if c.primary.restricted == c.shadow.restricted)
        elif test == "subtype":
            k = sum(1 for _, c in comparable if c.primary.subtype == c.shadow.subtype)
        elif test == "recipient_kind":
            k = sum(1 for _, c in comparable if c.primary.recipient_kind == c.shadow.recipient_kind)
        else:
            k = sum(1 for _, c in comparable if c.agrees_all)
        return proportion(k, n)

    confusion = Counter(
        (c.primary.category or "", c.shadow.category or "")
        for _, c in comparable
        if not c.agrees_category
    )
    reasons = Counter(
        c.shadow.unclassified_reason or "unknown"
        for _, c in everything
        if c.shadow.status != "classified"
    )
    corrected_lines = [(rid, c) for rid, c in everything if (rid, c.line_id) in corrected]
    scored = [(rid, c) for rid, c in corrected_lines if c.comparable]
    primary_k = sum(1 for rid, c in scored if c.primary.category == corrected[(rid, c.line_id)])
    shadow_k = sum(1 for rid, c in scored if c.shadow.category == corrected[(rid, c.line_id)])
    return AgreementReport(
        receipts=len(receipts),
        lines=len(everything),
        comparable=n,
        category=share("category"),
        restricted=share("restricted"),
        subtype=share("subtype"),
        recipient_kind=share("recipient_kind"),
        all_fields=share("all"),
        shadow_unclassified=dict(sorted(reasons.items())),
        confusion=[
            Confusion(primary, shadow, count)
            for (primary, shadow), count in sorted(
                confusion.items(), key=lambda item: (-item[1], item[0])
            )
        ],
        corrections=Corrections(
            corrected_lines=len(corrected_lines),
            n=len(scored),
            primary=proportion(primary_k, len(scored)),
            shadow=proportion(shadow_k, len(scored)),
        ),
    )
