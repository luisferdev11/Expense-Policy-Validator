"""The HTTP API: a FastAPI application over the use-case services.

It lives in `app/` because it calls the services, and adapters may not import `app/`
(ADR 0007 D2). The routes hold no business logic.
"""

from __future__ import annotations

from fastapi import FastAPI

from expense_validator.app.api.errors import install_error_handlers
from expense_validator.app.api.routes import build_router
from expense_validator.app.reviewing import ReviewService
from expense_validator.app.service import ReceiptService


def create_app(service: ReceiptService, review: ReviewService | None = None) -> FastAPI:
    """The application. Without a review service, one without tracing is built over `service`."""
    review = review or ReviewService(service.store, service.clock, service)
    app = FastAPI(
        title="Expense Policy Validator",
        version="0.3.0",
        description="Intake and lifecycle of expense receipts (ADR 0006, ADR 0007).",
    )
    install_error_handlers(app)
    app.include_router(build_router(service, review))
    return app


__all__ = ["create_app"]
