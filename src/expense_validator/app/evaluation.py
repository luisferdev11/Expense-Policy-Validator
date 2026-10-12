"""The evaluation step, shared by the worker and by the reviewer's category correction.

It runs inside a store transaction handed in by the caller. It loads a receipt's classifications
with the reviewers' corrections laid over the model's answers, adds the classified receipts that
share an employee-day or a trip, builds the cross-receipt context with the engine's own
`build_context`, and decides with the same function `epv run` uses (ADR 0007 D6, D9).
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime

from expense_validator.adapters.tracing import NoopTracer
from expense_validator.app.decide import decide_receipt
from expense_validator.domain.cascade import sharing_keys
from expense_validator.domain.engine.context import build_context
from expense_validator.domain.engine.settings import Settings
from expense_validator.domain.evaluation import result_hash
from expense_validator.domain.events import LineCategoryCorrected, ReceiptEvaluated
from expense_validator.domain.lifecycle import State, decision_after
from expense_validator.domain.models import (
    ClassifiedReceipt,
    CrossReceiptContext,
    ReceiptResult,
    RunMetadata,
)
from expense_validator.domain.review import apply_corrections, qa_sampled
from expense_validator.ports.store import ReceiptRecord, StoreTx, stamp


@dataclass(frozen=True)
class Evaluation:
    classified: ClassifiedReceipt
    context: CrossReceiptContext
    result: ReceiptResult
    digest: str


def load_classified(tx: StoreTx, receipt_id: str, revision: int) -> ClassifiedReceipt | None:
    """A revision with its classifications, the reviewers' corrections applied; None until the
    classify stage has run."""
    found = tx.get_revision(receipt_id, revision)
    classifications = tx.load_classifications(receipt_id, revision)
    if found is None or classifications is None:
        return None
    corrections = [
        (e.seq, e.event.line_id, e.event.to_category)
        for e in tx.list_events(receipt_id)
        if isinstance(e.event, LineCategoryCorrected) and e.revision == revision
    ]
    return ClassifiedReceipt(
        receipt=found.receipt,
        classifications=apply_corrections(classifications, receipt_id, revision, corrections),
    )


def build_evaluation(
    tx: StoreTx, settings: Settings, meta: RunMetadata, receipt_id: str, revision: int
) -> Evaluation:
    own = load_classified(tx, receipt_id, revision)
    if own is None:
        raise LookupError("the receipt has no classifications to evaluate")
    group = [own]
    for other_id in tx.current_receipts_sharing(sharing_keys(own.receipt)):
        other = tx.get_receipt(other_id)
        if other_id == receipt_id or other is None:
            continue
        neighbour = load_classified(tx, other_id, other.current_revision)
        if neighbour is not None:
            group.append(neighbour)
    context = build_context(group, settings)
    result = decide_receipt(own, context, meta, settings, NoopTracer(), "")
    return Evaluation(own, context, result, result_hash(result))


def queue_neighbours(tx: StoreTx, receipt_id: str, now: datetime) -> None:
    """Queue an evaluation for every classified receipt that shares a key with this one, old
    keys included, so a revision that moved also refreshes the group it left (D6)."""
    keys = tx.keys_of_receipt(receipt_id)
    for other_id in tx.current_receipts_sharing(keys):
        other = tx.get_receipt(other_id)
        if (
            other_id != receipt_id
            and other is not None
            and tx.load_classifications(other_id, other.current_revision) is not None
        ):
            tx.enqueue(other_id, other.current_revision, "evaluate", now)


def record_evaluation(
    tx: StoreTx,
    record: ReceiptRecord,
    evaluation: Evaluation,
    state: State,
    notice: str | None,
    actor: str,
    now: datetime,
) -> int:
    """Store a new evaluation version and move the receipt to `state`. Returns the version."""
    result = evaluation.result
    rid, revision = record.receipt_id, record.current_revision
    version = tx.add_evaluation(rid, revision, result, evaluation.digest, now)
    decided_by, decided_at = decision_after(
        state, actor=actor, at=stamp(now), by_human_action=False
    )
    tx.put_receipt(
        replace(
            record,
            state=state,
            decided_by=decided_by,
            decided_at=decided_at,
            disposition=result.disposition,
            evaluation_version=version,
            notice=notice,
            qa_sample=state == "auto_approved" and qa_sampled(rid, revision),
            failed_stage=None,
            failed_reason=None,
            updated_at=stamp(now),
        )
    )
    tx.append_event(
        rid,
        revision,
        ReceiptEvaluated(
            version=version,
            disposition=result.disposition,
            changed=True,
            result_hash=evaluation.digest,
        ),
        actor,
        now,
    )
    return version
