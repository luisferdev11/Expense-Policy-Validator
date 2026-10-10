"""The worker: claims outbox items and runs one stage at a time (ADR 0006 decision 1, ADR 0007).

Two stages per receipt revision.

- `classify`: the only stage that calls a model. The call happens outside any database
  transaction; its answer and the event commit together afterwards. A crash before the commit
  leaves the item leased, the lease expires, and the stage is repeated; the classification cache
  answers a repeated call for free and identically, so no extra billed call is made.
- `evaluate`: pure (see `app/evaluation.py`). The whole stage is one transaction, so a change
  that lands meanwhile cannot slip between the read and the write, and a new evaluation version
  is stored only if the result changed.

When a receipt is classified, an `evaluate` is queued for it and for every classified receipt
that shares a key with it, so the result at rest does not depend on arrival order (D6).
"""

from __future__ import annotations

import re
import threading
from dataclasses import replace
from datetime import timedelta

from expense_validator.adapters.config_files import PipelineConfig
from expense_validator.app.decide import decide_receipt
from expense_validator.app.evaluation import (
    build_evaluation,
    queue_neighbours,
    record_evaluation,
)
from expense_validator.app.pipeline import classify_receipt, run_metadata
from expense_validator.domain.engine.settings import Settings
from expense_validator.domain.events import (
    NoticeRaised,
    ReceiptClassified,
    StageFailed,
)
from expense_validator.domain.lifecycle import (
    Stage,
    reevaluation_outcome,
    state_for_evaluation,
)
from expense_validator.ports.classifier import ItemClassifier
from expense_validator.ports.store import Clock, ReceiptStore, WorkItem
from expense_validator.ports.tracer import Tracer

WORKER = "worker"
LEASE = timedelta(seconds=60)
MAX_ATTEMPTS = 3
# Reasons a line comes back unclassified because the service could not answer, not because of
# the answer itself. They are not results: the stage fails and is retried. `schema_violation`
# and `offline_cache_miss` are final and stay results (EXC-03 asks for a review).
TRANSIENT_REASONS = frozenset({"gateway_error", "budget_refused"})
_SECRET = re.compile(r"(sk-|pk-|lf-)[A-Za-z0-9_\-.*]+")


class ClassificationUnavailableError(Exception):
    """The classifier could not answer for at least one line."""


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
        unavailable = sorted(
            {
                c.unclassified_reason
                for c in classified.classifications
                if c.unclassified_reason in TRANSIENT_REASONS
            }
        )
        if unavailable:
            # The adapter reports an outage as an answer, not as an error. Saving it would send a
            # receipt that was never classified to a person, and nothing would retry it.
            raise ClassificationUnavailableError(
                "the classifier could not answer: " + ", ".join(unavailable)
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
            queue_neighbours(tx, rid, now)

    def _evaluate(self, item: WorkItem) -> None:
        rid, revision = item.receipt_id, item.revision
        now = self.clock()
        traced = None
        with self.store.transaction() as tx:
            record = tx.get_receipt(rid)
            if record is None or record.current_revision != revision:
                tx.complete_work(item.id)
                return
            evaluation = build_evaluation(tx, self.settings, self.meta, rid, revision)
            latest = tx.latest_evaluation(rid, revision)
            tx.complete_work(item.id)
            if latest is not None and latest.result_hash == evaluation.digest:
                if record.failed_stage is not None:  # the stage succeeded: the failure is over
                    tx.put_receipt(
                        replace(
                            record,
                            failed_stage=None,
                            failed_reason=None,
                            updated_at=now.isoformat(),
                        )
                    )
                return
            result = evaluation.result
            critical = any(e.severity == "critical" for e in result.exceptions)
            proposed = state_for_evaluation(result.disposition, critical)
            notice = record.notice
            raised: str | None = None
            if latest is None:
                state = proposed
            else:
                state, flag = reevaluation_outcome(record.state, record.human_acted, proposed)
                if flag:
                    after = "your decision" if record.human_acted else "a re-evaluation"
                    raised = (
                        f"The result changed after {after}: "
                        f"{latest.result.disposition} became {result.disposition}."
                    )
                    notice = raised
            version = record_evaluation(tx, record, evaluation, state, notice, WORKER, now)
            if raised is not None:
                tx.append_event(rid, revision, NoticeRaised(text=raised), WORKER, now)
            traced = (evaluation, f"app-r{revision}-v{version}")
        if traced is not None:
            decided, label = traced
            decide_receipt(
                decided.classified, decided.context, self.meta, self.settings, self.tracer, label
            )

    # Failure

    def _fail(self, item: WorkItem, reason: str) -> None:
        stage: Stage = item.stage
        now = self.clock()
        with self.store.transaction() as tx:
            tx.fail_work(item.id, reason)
            record = tx.get_receipt(item.receipt_id)
            if record is not None and record.current_revision == item.revision:
                # A receipt that was already evaluated keeps its state (a decision must not
                # disappear because a later re-evaluation failed); the failure is shown on it and
                # a retry runs the stage again. Only a receipt with no evaluation is `failed`.
                evaluated = record.evaluation_version is not None
                tx.put_receipt(
                    replace(
                        record,
                        state=record.state if evaluated else "failed",
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
