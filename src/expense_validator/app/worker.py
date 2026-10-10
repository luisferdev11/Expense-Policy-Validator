"""The worker: claims outbox items and runs one stage at a time (ADR 0006 decision 1, ADR 0007).

Two stages per receipt revision.

- `classify`: the only stage that calls a model. The call happens outside any database
  transaction; its answer and the event commit together afterwards. A crash before the commit
  leaves the item leased, the lease expires, and the stage is repeated; the classification cache
  answers a repeated call for free and identically, so no extra billed call is made.
- `evaluate`: pure. It reads the receipt and the classified receipts that share an employee-day
  or a trip with it, builds the cross-receipt context with the engine's own `build_context`,
  decides, and stores a new evaluation version only if the result changed. The whole stage is one
  transaction, so a change that lands meanwhile cannot slip between the read and the write.

When a receipt is classified, an `evaluate` is queued for it and for every classified receipt
that shares a key with it, so the result at rest does not depend on arrival order (D6).
"""

from __future__ import annotations

import re
import threading
from dataclasses import replace
from datetime import timedelta

from expense_validator.adapters.config_files import PipelineConfig
from expense_validator.adapters.tracing import NoopTracer
from expense_validator.app.decide import decide_receipt
from expense_validator.app.pipeline import classify_receipt, run_metadata
from expense_validator.domain.cascade import sharing_keys
from expense_validator.domain.engine.context import build_context
from expense_validator.domain.engine.settings import Settings
from expense_validator.domain.evaluation import result_hash
from expense_validator.domain.events import (
    NoticeRaised,
    ReceiptClassified,
    ReceiptEvaluated,
    StageFailed,
)
from expense_validator.domain.lifecycle import (
    Stage,
    reevaluation_outcome,
    state_for_evaluation,
)
from expense_validator.domain.models import ClassifiedReceipt, ReceiptResult
from expense_validator.domain.review import qa_sampled
from expense_validator.ports.classifier import ItemClassifier
from expense_validator.ports.store import Clock, ReceiptStore, StoreTx, WorkItem
from expense_validator.ports.tracer import Tracer

WORKER = "worker"
LEASE = timedelta(seconds=60)
MAX_ATTEMPTS = 3
_SECRET = re.compile(r"(sk-|pk-|lf-)[A-Za-z0-9_\-.*]+")


def scrub(message: str, limit: int = 300) -> str:
    """A failure reason that is safe to store and show: no key-like token, bounded length."""
    return _SECRET.sub("[redacted]", message)[:limit]


class Worker:
    def __init__(
        self,
        store: ReceiptStore,
        classifier: ItemClassifier,
        tracer: Tracer,
        settings: Settings,
        clock: Clock,
        config: PipelineConfig | None = None,
        *,
        lease: timedelta = LEASE,
        max_attempts: int = MAX_ATTEMPTS,
    ) -> None:
        self.store = store
        self.classifier = classifier
        self.tracer = tracer
        self.settings = settings
        self.clock = clock
        self.lease = lease
        self.max_attempts = max_attempts
        self.meta = run_metadata(classifier, settings, config)

    # Loop

    def process_next(self) -> bool:
        """Claim and run one item. False when nothing is claimable."""
        now = self.clock()
        with self.store.transaction() as tx:
            item = tx.claim_work(now, now + self.lease)
        if item is None:
            return False
        if item.attempts > self.max_attempts:
            self._fail(item, f"gave up after {self.max_attempts} attempts")
            return True
        try:
            if item.stage == "classify":
                self._classify(item)
            else:
                self._evaluate(item)
        except Exception as exc:
            self._fail(item, f"{type(exc).__name__}: {scrub(str(exc))}")
        return True

    def run_once(self) -> int:
        """Drain the queue and return the number of items processed."""
        processed = 0
        while self.process_next():
            processed += 1
        self.tracer.flush()
        return processed

    def run_forever(self, poll_seconds: float = 1.0, stop: threading.Event | None = None) -> None:
        stop = stop or threading.Event()
        while not stop.is_set():
            if self.run_once() == 0:
                stop.wait(poll_seconds)

    # Stages

    def _classify(self, item: WorkItem) -> None:
        rid, revision = item.receipt_id, item.revision
        now = self.clock()
        with self.store.transaction() as tx:
            record = tx.get_receipt(rid)
            found = tx.get_revision(rid, revision)
            if record is None or found is None or record.current_revision != revision:
                tx.complete_work(item.id)
                return
            if record.state in ("submitted", "failed"):
                tx.put_receipt(
                    replace(
                        record,
                        state="classifying",
                        failed_stage=None,
                        failed_reason=None,
                        updated_at=now.isoformat(),
                    )
                )
        calls_before = getattr(self.classifier, "calls_made", 0)
        hits_before = getattr(self.classifier, "cache_hits", 0)
        classified = classify_receipt(
            found.receipt, self.classifier, self.tracer, f"app-r{revision}-c"
        )
        now = self.clock()
        with self.store.transaction() as tx:
            record = tx.get_receipt(rid)
            if record is None or record.current_revision != revision:
                tx.complete_work(item.id)  # a newer revision replaced this one meanwhile
                return
            tx.save_classifications(rid, revision, classified.classifications)
            tx.append_event(
                rid,
                revision,
                ReceiptClassified(
                    lines=len(classified.classifications),
                    cache_hits=getattr(self.classifier, "cache_hits", 0) - hits_before,
                    calls_made=getattr(self.classifier, "calls_made", 0) - calls_before,
                ),
                WORKER,
                now,
            )
            tx.complete_work(item.id)
            tx.enqueue(rid, revision, "evaluate", now)
            for other_id in self._affected(tx, rid):
                other = tx.get_receipt(other_id)
                if other is not None and tx.load_classifications(other_id, other.current_revision):
                    tx.enqueue(other_id, other.current_revision, "evaluate", now)

    def _affected(self, tx: StoreTx, receipt_id: str) -> list[str]:
        """Receipts that share a key with any revision of this one, old keys included, so a
        revision that moved to another day or trip also refreshes the group it left."""
        return [
            r
            for r in tx.current_receipts_sharing(tx.keys_of_receipt(receipt_id))
            if r != receipt_id
        ]

    def _evaluate(self, item: WorkItem) -> None:
        rid, revision = item.receipt_id, item.revision
        now = self.clock()
        traced: tuple[ClassifiedReceipt, str] | None = None
        with self.store.transaction() as tx:
            record = tx.get_receipt(rid)
            if record is None or record.current_revision != revision:
                tx.complete_work(item.id)
                return
            own = self._classified(tx, rid, revision)
            if own is None:
                raise LookupError("the receipt has no classifications to evaluate")
            group = [own]
            for other_id in tx.current_receipts_sharing(sharing_keys(own.receipt)):
                other = tx.get_receipt(other_id)
                if other_id == rid or other is None:
                    continue
                neighbour = self._classified(tx, other_id, other.current_revision)
                if neighbour is not None:
                    group.append(neighbour)
            context = build_context(group, self.settings)
            result = decide_receipt(own, context, self.meta, self.settings, NoopTracer(), "")
            digest = result_hash(result)
            latest = tx.latest_evaluation(rid, revision)
            tx.complete_work(item.id)
            if latest is not None and latest.result_hash == digest:
                return
            version = tx.add_evaluation(rid, revision, result, digest, now)
            self._apply_evaluation(
                tx, rid, revision, version, result, digest, latest.result if latest else None
            )
            traced = (own, f"app-r{revision}-v{version}")
        if traced is not None:
            decide_receipt(traced[0], context, self.meta, self.settings, self.tracer, traced[1])

    def _classified(self, tx: StoreTx, receipt_id: str, revision: int) -> ClassifiedReceipt | None:
        found = tx.get_revision(receipt_id, revision)
        classifications = tx.load_classifications(receipt_id, revision)
        if found is None or classifications is None:
            return None
        return ClassifiedReceipt(receipt=found.receipt, classifications=classifications)

    def _apply_evaluation(
        self,
        tx: StoreTx,
        rid: str,
        revision: int,
        version: int,
        result: ReceiptResult,
        digest: str,
        previous: ReceiptResult | None,
    ) -> None:
        now = self.clock()
        record = tx.get_receipt(rid)
        assert record is not None
        critical = any(e.severity == "critical" for e in result.exceptions)
        proposed = state_for_evaluation(result.disposition, critical)
        notice = record.notice
        raised: str | None = None
        if previous is None:
            state = proposed
        else:
            state, flag = reevaluation_outcome(record.state, record.human_acted, proposed)
            if flag:
                raised = (
                    f"The result changed after a re-evaluation: "
                    f"{previous.disposition} became {result.disposition}."
                )
                notice = raised
        tx.put_receipt(
            replace(
                record,
                state=state,
                disposition=result.disposition,
                evaluation_version=version,
                notice=notice,
                qa_sample=state == "auto_approved" and qa_sampled(rid, revision),
                failed_stage=None,
                failed_reason=None,
                updated_at=now.isoformat(),
            )
        )
        tx.append_event(
            rid,
            revision,
            ReceiptEvaluated(
                version=version, disposition=result.disposition, changed=True, result_hash=digest
            ),
            WORKER,
            now,
        )
        if raised is not None:
            tx.append_event(rid, revision, NoticeRaised(text=raised), WORKER, now)

    # Failure

    def _fail(self, item: WorkItem, reason: str) -> None:
        stage: Stage = item.stage
        now = self.clock()
        with self.store.transaction() as tx:
            tx.fail_work(item.id, reason)
            record = tx.get_receipt(item.receipt_id)
            if record is not None and record.current_revision == item.revision:
                tx.put_receipt(
                    replace(
                        record,
                        state="failed",
                        failed_stage=stage,
                        failed_reason=reason,
                        updated_at=now.isoformat(),
                    )
                )
                tx.append_event(
                    item.receipt_id,
                    item.revision,
                    StageFailed(stage=stage, reason=reason),
                    WORKER,
                    now,
                )
