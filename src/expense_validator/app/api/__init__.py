"""The HTTP API: a FastAPI application over the use-case services.

It lives in `app/` because it calls the services, and adapters may not import `app/`
(ADR 0007 D2). The routes hold no business logic.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from expense_validator.app.api.errors import install_error_handlers
from expense_validator.app.api.routes import build_router
from expense_validator.app.batching import BatchService
from expense_validator.app.reviewing import ReviewService
from expense_validator.app.service import ReceiptService
from expense_validator.domain.models import ReceiptInput

# The origins of a local front end: the Vite dev server and its preview. A deployment lists its own
# (`--cors-origin` or `EPV_CORS_ORIGINS`). A browser blocks calls to another origin unless the API
# answers with CORS headers; no origin outside this list gets any.
DEFAULT_CORS_ORIGINS = (
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:4173",
    "http://127.0.0.1:4173",
)


def add_request_schemas(document: dict[str, Any]) -> None:
    """Add the schema of what a client submits: `ReceiptInputRequest` and `LineItemInputRequest`.

    The response schemas, `ReceiptInput` and `LineItemInput`, are generated in serialization mode
    (money is a string). A client may send money as a number or a string, which is the validation
    mode's schema, so it gets its own names: every `$defs` key and every reference carries the
    `Request` suffix, which cannot collide with a response schema (spec 006, research R10).
    """
    schemas = document.setdefault("components", {}).setdefault("schemas", {})
    schema = ReceiptInput.model_json_schema(
        mode="validation", ref_template="#/components/schemas/{model}Request"
    )
    definitions = schema.pop("$defs", {})
    renamed = {"ReceiptInputRequest": schema}
    renamed.update({f"{name}Request": sub for name, sub in definitions.items()})
    for name, sub in renamed.items():
        if name in schemas:
            raise ValueError(f"the OpenAPI component {name} already exists")
        sub["title"] = name
        schemas[name] = sub


def _install_openapi(app: FastAPI) -> None:
    generate = app.openapi

    def openapi() -> dict[str, Any]:
        if app.openapi_schema is None:
            add_request_schemas(generate())  # builds and caches the document, then adds to it
        return app.openapi_schema or {}

    app.openapi = openapi  # type: ignore[method-assign]


def create_app(
    service: ReceiptService,
    review: ReviewService | None = None,
    batches: BatchService | None = None,
    cors_origins: Sequence[str] | None = None,
) -> FastAPI:
    """The application. Without a review service, one without tracing is built over `service`."""
    review = review or ReviewService(service.store, service.clock, service)
    app = FastAPI(
        title="Expense Policy Validator",
        version="1.1.0",
        description="Intake and lifecycle of expense receipts (ADR 0006, ADR 0007).",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(DEFAULT_CORS_ORIGINS if cors_origins is None else cors_origins),
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "Idempotency-Key"],
    )
    install_error_handlers(app)
    app.include_router(build_router(service, review, batches or BatchService(service)))
    _install_openapi(app)
    return app


__all__ = ["DEFAULT_CORS_ORIGINS", "create_app"]
