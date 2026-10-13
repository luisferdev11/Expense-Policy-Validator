"""`epv shadow report`: how a shadow classifier compares with the deciding one (spec 007, FR-016).

Everything comes from the store: the deciding classifier's stored answers, the shadow's rows and the
reviewers' corrections. No model is called and no answer label is read. The disposition impact
re-runs the engine's unchanged decision code twice over the receipts the shadow answered in full,
once with each classifier's answers and with the cross-receipt context built from that same set, and
counts how many receipts end up with another disposition.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import asdict, dataclass
from typing import Any

from expense_validator.adapters.tracing import NoopTracer
from expense_validator.app.decide import decide_receipt
from expense_validator.domain.engine.context import build_context
from expense_validator.domain.engine.settings import Settings
from expense_validator.domain.events import LineCategoryCorrected
from expense_validator.domain.models import ClassifiedReceipt, RunMetadata
from expense_validator.domain.shadow import (
    AgreementReport,
    LineComparison,
    Proportion,
    agreement,
    compare,
    proportion,
)
from expense_validator.ports.store import ReceiptStore, ShadowRecord


@dataclass(frozen=True)
class DispositionImpact:
    """Receipts whose disposition would differ had the shadow's answers decided."""

    receipts: Proportion  # k differ of n answered in full by the shadow
    changes: dict[str, int]  # "review->pass": how many receipts


@dataclass(frozen=True)
class ShadowReportData:
    classifier: str
    agreement: AgreementReport
    disposition: DispositionImpact


def _disposition_impact(
    primary: list[ClassifiedReceipt],
    shadow: list[ClassifiedReceipt],
    metas: list[RunMetadata],
    settings: Settings,
) -> DispositionImpact:
    primary_context = build_context(primary, settings)
    shadow_context = build_context(shadow, settings)
    changes: Counter[str] = Counter()
    for p, s, meta in zip(primary, shadow, metas, strict=True):
        before = decide_receipt(p, primary_context, meta, settings, NoopTracer(), "").disposition
        after = decide_receipt(s, shadow_context, meta, settings, NoopTracer(), "").disposition
        if before != after:
            changes[f"{before}->{after}"] += 1
    return DispositionImpact(
        receipts=proportion(sum(changes.values()), len(primary)),
        changes=dict(sorted(changes.items())),
    )


def build_shadow_report(
    store: ReceiptStore, settings: Settings, classifier: str | None = None
) -> list[ShadowReportData]:
    """One report per shadow classifier in the store, over the current revision of each receipt.
    A revision that has been replaced is not counted."""
    reports: list[ShadowReportData] = []
    with store.transaction(write=False) as tx:
        rows = list(tx.iter_shadow(classifier))
        for name in sorted({r.classifier for r in rows}):
            by_receipt: dict[str, list[ShadowRecord]] = {}
            for r in rows:
                if r.classifier == name:
                    by_receipt.setdefault(r.receipt_id, []).append(r)
            pairs: list[tuple[str, list[LineComparison]]] = []
            corrected: dict[tuple[str, str], str] = {}
            primary_group: list[ClassifiedReceipt] = []
            shadow_group: list[ClassifiedReceipt] = []
            metas: list[RunMetadata] = []
            for rid, receipt_rows in by_receipt.items():
                record = tx.get_receipt(rid)
                if record is None:
                    continue
                revision = record.current_revision
                current = [r for r in receipt_rows if r.revision == revision]
                primary = tx.load_classifications(rid, revision)
                found = tx.get_revision(rid, revision)
                if not current or primary is None or found is None:
                    continue
                shadow_answers = [r.classification for r in current]
                pairs.append((rid, compare(primary, shadow_answers)))
                for e in tx.list_events(rid):
                    if isinstance(e.event, LineCategoryCorrected) and e.revision == revision:
                        corrected[(rid, e.event.line_id)] = e.event.to_category
                by_line = {c.line_id: c for c in shadow_answers}
                evaluation = tx.latest_evaluation(rid, revision)
                answered = all(
                    line.line_id in by_line and by_line[line.line_id].status == "classified"
                    for line in found.receipt.line_items
                )
                if answered and evaluation is not None:
                    primary_group.append(
                        ClassifiedReceipt(receipt=found.receipt, classifications=primary)
                    )
                    shadow_group.append(
                        ClassifiedReceipt(
                            receipt=found.receipt,
                            classifications=tuple(
                                by_line[line.line_id] for line in found.receipt.line_items
                            ),
                        )
                    )
                    metas.append(evaluation.result.run)
            reports.append(
                ShadowReportData(
                    classifier=name,
                    agreement=agreement(pairs, corrected),
                    disposition=_disposition_impact(primary_group, shadow_group, metas, settings),
                )
            )
    return reports


def to_dict(report: ShadowReportData) -> dict[str, Any]:
    """The report as plain JSON types (tuples become lists)."""
    document: dict[str, Any] = json.loads(json.dumps(asdict(report)))
    return document


def _pct(p: Proportion) -> str:
    if p.rate is None or p.interval is None:
        return f"{p.k}/{p.n} (no comparable lines)"
    low, high = p.interval
    return f"{p.k}/{p.n} = {p.rate * 100:.1f} % (95 % CI {low * 100:.1f} to {high * 100:.1f} %)"


def render(reports: list[ShadowReportData]) -> str:
    if not reports:
        return "epv shadow report: no shadow answers in this store\n"
    out: list[str] = []
    for report in reports:
        a = report.agreement
        out += [
            f"epv shadow report: {report.classifier}",
            f"  receipts with shadow answers (current revision): {a.receipts}, lines: {a.lines}, "
            f"comparable (both classified): {a.comparable}",
            f"  category agreement: {_pct(a.category)}",
            f"  restricted flag agreement: {_pct(a.restricted)}",
            f"  subtype agreement: {_pct(a.subtype)}",
            f"  recipient kind agreement: {_pct(a.recipient_kind)}",
            f"  every field agreement: {_pct(a.all_fields)}",
        ]
        if a.shadow_unclassified:
            reasons = ", ".join(f"{r} {n}" for r, n in a.shadow_unclassified.items())
            out.append(f"  shadow lines it could not classify: {reasons}")
        if a.confusion:
            out.append("  disagreements, deciding -> shadow:")
            out += [f"    {c.primary} -> {c.shadow}: {c.count}" for c in a.confusion]
        c = a.corrections
        out.append(
            f"  reviewer corrections: {c.corrected_lines} corrected lines, {c.n} answered by both"
            f"; deciding matched {_pct(c.primary)}; shadow matched {_pct(c.shadow)}"
        )
        d = report.disposition
        out.append(
            f"  disposition would differ for {_pct(d.receipts)} of the receipts the shadow "
            "answered in full"
        )
        out += [f"    {change}: {n}" for change, n in d.changes.items()]
        out.append("")
    return "\n".join(out)
