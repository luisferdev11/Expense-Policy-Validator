"""Routes. Each one calls the service and shapes the response; nothing else."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Header, Query, Request, Response
from starlette.concurrency import run_in_threadpool

from expense_validator.app.api.schemas import (
    ActionBody,
    ActionResponse,
    EventItem,
    EventList,
    Health,
    ReceiptDetail,
    ReceiptList,
    ReceiptSummary,
    RevisionDetail,
    SubmitResponse,
)
from expense_validator.app.errors import NotFoundError
from expense_validator.app.reviewing import ActionRequest, ReviewService
from expense_validator.app.service import ReceiptService
from expense_validator.domain.lifecycle import ACTIONS

# The body is read raw, not through a model: money must keep its written precision, and a
# float parsed by the framework would lose it.
_RECEIPT_BODY = {
    "requestBody": {
        "required": True,
        "content": {"application/json": {"schema": {"type": "object"}}},
    }
}


def build_router(service: ReceiptService, review: ReviewService) -> APIRouter:
    router = APIRouter()

    @router.get("/health", response_model=Health, tags=["operations"])
    def health() -> Health:
        return Health(status="ok", schema_version=service.store.schema_version)

    @router.post(
        "/receipts",
        response_model=SubmitResponse,
        status_code=202,
        tags=["receipts"],
        openapi_extra=_RECEIPT_BODY,
    )
    async def submit_receipt(
        request: Request,
        response: Response,
        idempotency_key: Annotated[str | None, Header()] = None,
    ) -> SubmitResponse:
        body = await request.body()
        outcome = await run_in_threadpool(service.submit, body, idempotency_key)
        if outcome.outcome == "existing":
            response.status_code = 200
        return SubmitResponse.of(outcome)

    @router.get("/receipts", response_model=ReceiptList, tags=["receipts"])
    def list_receipts(
        state: str | None = None,
        disposition: str | None = None,
        batch_id: str | None = None,
        limit: Annotated[int, Query(ge=1, le=500)] = 100,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> ReceiptList:
        records, total = service.list_receipts(
            state=state, disposition=disposition, batch_id=batch_id, limit=limit, offset=offset
        )
        return ReceiptList(items=[ReceiptSummary.of(r) for r in records], total=total)

    @router.get("/receipts/{receipt_id}", response_model=ReceiptDetail, tags=["receipts"])
    def get_receipt(receipt_id: str) -> ReceiptDetail:
        return ReceiptDetail.from_view(service.get_receipt(receipt_id))

    @router.post(
        "/receipts/{receipt_id}/retry",
        response_model=ReceiptSummary,
        status_code=202,
        tags=["receipts"],
    )
    def retry_receipt(receipt_id: str) -> ReceiptSummary:
        return ReceiptSummary.of(service.retry(receipt_id))

    @router.post(
        "/receipts/{receipt_id}/actions/{action}",
        response_model=ActionResponse,
        tags=["review"],
        summary="A reviewer's action: " + ", ".join(ACTIONS),
    )
    def review_action(receipt_id: str, action: str, body: ActionBody) -> ActionResponse:
        chosen = next((a for a in ACTIONS if a == action), None)
        if chosen is None:
            raise NotFoundError(f"no action {action!r}", {"actions": list(ACTIONS)})
        result = review.act(receipt_id, chosen, ActionRequest(**body.model_dump()))
        return ActionResponse.from_result(result)

    @router.get("/receipts/{receipt_id}/events", response_model=EventList, tags=["receipts"])
    def get_events(receipt_id: str) -> EventList:
        return EventList(items=[EventItem.of(e) for e in service.list_events(receipt_id)])

    @router.get(
        "/receipts/{receipt_id}/revisions/{revision}",
        response_model=RevisionDetail,
        tags=["receipts"],
    )
    def get_revision(receipt_id: str, revision: int) -> RevisionDetail:
        return RevisionDetail.of(service.get_revision(receipt_id, revision))

    return router
