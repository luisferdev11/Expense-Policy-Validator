"""Reviewer actions on an evaluated receipt (ADR 0006 decision 6, ADR 0007 D8 to D10).

Approve or reject, correct a line's category, request information, escalate to Compliance. Each
action is one transaction: its event, the projection and, for a correction, the new evaluation
version commit together. A correction re-runs the engine in that same transaction, with the human
category laid over the model's answer, so the reviewer gets the new proposal in the response and no
"result changed" notice is raised for a change the reviewer caused. Receipts that share a day or
a trip are queued for re-evaluation, as for any other classification change.

Scoring in Langfuse is best effort: it happens after the commit and can never fail an action.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime

from expense_validator.adapters.config_files import load_settings
from expense_validator.adapters.tracing import NoopTracer
from expense_validator.app.decide import decide_receipt
from expense_validator.app.errors import (
    ActionNotAllowedError,
    InvalidActionError,
    NotFoundError,
    ReasonRequiredError,
    StaleEvaluationError,
    UnknownCategoryError,
)
from expense_validator.app.evaluation import (
    Evaluation,
    build_evaluation,
    load_classified,
    queue_neighbours,
    record_evaluation,
)
from expense_validator.app.service import ReceiptService, ReceiptView
from expense_validator.domain.engine.settings import Settings
from expense_validator.domain.events import (
    DevCandidateMarked,
    EscalatedToCompliance,
    InformationRequested,
    LineCategoryCorrected,
    ReceiptApproved,
    ReceiptRejected,
)
from expense_validator.domain.lifecycle import (
    Action,
    NotAllowedError,
    allowed_actions,
    decision_after,
    require_allowed,
    state_after_action,
    state_after_correction,
    state_for_evaluation,
)
from expense_validator.domain.models import Disposition, RunMetadata
from expense_validator.domain.review import REASON_CODES, agreement, requires_reason
from expense_validator.domain.taxonomy import CATEGORIES
from expense_validator.ports.store import Clock, ReceiptRecord, ReceiptStore, StoreTx, stamp
from expense_validator.ports.tracer import Tracer

AGREEMENT_SCORE = "auditor_agreement"


@dataclass(frozen=True)
class ActionRequest:
    """What a reviewer sends. `evaluation_version` is the one they saw (stale actions are
    refused). The other fields apply to some actions only."""

    actor: str
    evaluation_version: int
    note: str | None = None
    reason_code: str | None = None
    line_id: str | None = None
    category: str | None = None
    question: str | None = None
    reason: str | None = None


@dataclass(frozen=True)
class ActionResult:
    view: ReceiptView
    agreement: int


@dataclass(frozen=True)
class _Traced:
    evaluation: Evaluation
    meta: RunMetadata
    version: int


class ReviewService:
    def __init__(
        self,
        store: ReceiptStore,
        clock: Clock,
        receipts: ReceiptService,
        *,
        tracer: Tracer | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.store = store
        self.clock = clock
        self.receipts = receipts
        self.tracer: Tracer = tracer or NoopTracer()
        self.settings = settings or load_settings()

    def act(self, receipt_id: str, action: Action, request: ActionRequest) -> ActionResult:
        actor = request.actor.strip()
        if not actor:
            raise InvalidActionError("an actor is required")
        now = self.clock()
        traced: _Traced | None = None
        with self.store.transaction() as tx:
            record = tx.get_receipt(receipt_id)
            if record is None:
                raise NotFoundError(f"no receipt {receipt_id!r}")
            self._check(record, action, request)
            assert record.disposition is not None  # an allowed state always has an evaluation
            proposal = record.disposition
            agree = agreement(action, proposal)
            if action == "correct-category":
                traced = self._correct(tx, record, request, actor, agree, now)
            else:
                self._decide(tx, record, action, request, actor, agree, proposal, now)
        self._observe(receipt_id, record, action, proposal, request, agree, traced)
        return ActionResult(self.receipts.get_receipt(receipt_id), agree)

    # Validation

    def _check(self, record: ReceiptRecord, action: Action, request: ActionRequest) -> None:
        try:
            require_allowed(record.state, action)
        except NotAllowedError as exc:
            raise ActionNotAllowedError(
                str(exc),
                {"state": record.state, "allowed": list(allowed_actions(record.state))},
            ) from exc
        if record.evaluation_version != request.evaluation_version:
            raise StaleEvaluationError(
                "the receipt was evaluated again since you looked at it",
                {"current_evaluation_version": record.evaluation_version},
            )

    # Actions without a new evaluation

    def _decide(
        self,
        tx: StoreTx,
        record: ReceiptRecord,
        action: Action,
        request: ActionRequest,
        actor: str,
        agree: int,
        proposal: Disposition,
        now: datetime,
    ) -> None:
        rid, revision = record.receipt_id, record.current_revision
        version = request.evaluation_version
        event: ReceiptApproved | ReceiptRejected | InformationRequested | EscalatedToCompliance
        if action in ("approve", "reject"):
            code = self._reason_code(action, proposal, request)
            cls = ReceiptApproved if action == "approve" else ReceiptRejected
            event = cls(
                based_on_version=version, reason_code=code, note=request.note, agreement=agree
            )
        elif action == "request-info":
            question = _required(request.question, "a question to ask the employee")
            event = InformationRequested(
                question=question, based_on_version=version, agreement=agree
            )
        else:
            reason = _required(request.reason, "a reason to escalate")
            event = EscalatedToCompliance(reason=reason, based_on_version=version, agreement=agree)
        tx.append_event(rid, revision, event, actor, now)
        new_state = state_after_action(action)
        decided_by, decided_at = decision_after(
            new_state, actor=actor, at=stamp(now), by_human_action=True
        )
        tx.put_receipt(
            replace(
                record,
                state=new_state,
                human_acted=True,
                notice=None,
                updated_at=stamp(now),
                decided_by=decided_by,
                decided_at=decided_at,
            )
        )

    def _reason_code(
        self, action: Action, proposal: Disposition, request: ActionRequest
    ) -> str | None:
        code = request.reason_code
        if code is not None and code not in REASON_CODES:
            raise InvalidActionError("unknown reason code", {"allowed": list(REASON_CODES)})
        if requires_reason(action, proposal) and code is None:
            raise ReasonRequiredError(
                f"{action} overrides a {proposal} proposal and needs a reason code",
                {"allowed": list(REASON_CODES)},
            )
        if code == "other" and not (request.note and request.note.strip()):
            raise ReasonRequiredError("the reason code 'other' needs a note")
        return code

    # Category correction

    def _correct(
        self,
        tx: StoreTx,
        record: ReceiptRecord,
        request: ActionRequest,
        actor: str,
        agree: int,
        now: datetime,
    ) -> _Traced:
        rid, revision = record.receipt_id, record.current_revision
        line_id = _required(request.line_id, "line_id")
        category = _required(request.category, "category")
        if category not in CATEGORIES:
            raise UnknownCategoryError(
                f"{category!r} is not a taxonomy category", {"allowed": list(CATEGORIES)}
            )
        own = load_classified(tx, rid, revision)
        assert own is not None
        line = next((c for c in own.classifications if c.line_id == line_id), None)
        if line is None:
            raise InvalidActionError(f"no line {line_id!r} in this receipt")
        if line.category == category:
            raise InvalidActionError(f"the line already has the category {category!r}")
        tx.append_event(
            rid,
            revision,
            LineCategoryCorrected(
                line_id=line_id,
                from_category=line.category,
                to_category=category,
                based_on_version=request.evaluation_version,
                agreement=agree,
            ),
            actor,
            now,
        )
        tx.append_event(
            rid,
            revision,
            DevCandidateMarked(line_id=line_id, from_category=line.category, to_category=category),
            actor,
            now,
        )
        latest = tx.latest_evaluation(rid, revision)
        assert latest is not None
        meta = latest.result.run
        acted = replace(record, human_acted=True, notice=None)
        evaluation = build_evaluation(tx, self.settings, meta, rid, revision)
        critical = any(e.severity == "critical" for e in evaluation.result.exceptions)
        state = state_after_correction(
            state_for_evaluation(evaluation.result.disposition, critical)
        )
        version = record_evaluation(tx, acted, evaluation, state, None, actor, now)
        queue_neighbours(tx, rid, now)
        return _Traced(evaluation, meta, version)

    # After the commit: best effort

    def _observe(
        self,
        receipt_id: str,
        record: ReceiptRecord,
        action: Action,
        proposal: Disposition,
        request: ActionRequest,
        agree: int,
        traced: _Traced | None,
    ) -> None:
        try:
            if traced is not None:
                ev = traced.evaluation
                decide_receipt(
                    ev.classified,
                    ev.context,
                    traced.meta,
                    self.settings,
                    self.tracer,
                    f"app-r{record.current_revision}",
                    traced.version,
                )
            comment = f"{action}; proposal={proposal}"
            if request.reason_code:
                comment += f"; reason_code={request.reason_code}"
            comment += f"; evaluation_version={record.evaluation_version}"
            label = f"app-r{record.current_revision}"
            self.tracer.score(label, receipt_id, AGREEMENT_SCORE, float(agree), comment)
        except Exception:  # Langfuse never gates an action (constitution X)
            return


def _required(value: str | None, what: str) -> str:
    if value is None or not value.strip():
        raise InvalidActionError(f"{what} is required")
    return value.strip()
