"""One error shape for every failure: {"error": {"code", "message", "details"}}."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from expense_validator.app.errors import AppError

STATUS_BY_CODE: dict[str, int] = {
    "invalid_receipt": 422,
    "invalid_idempotency_key": 422,
    "idempotency_key_reuse": 422,
    "reason_required": 422,
    "unknown_category": 422,
    "invalid_action": 422,
    "not_found": 404,
    "action_not_allowed": 409,
    "stale_evaluation": 409,
}
_HTTP_CODES = {404: "not_found", 405: "method_not_allowed"}


def error_body(code: str, message: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"error": {"code": code, "message": message, "details": details or {}}}


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError) -> JSONResponse:
        status = STATUS_BY_CODE.get(exc.code, 400)
        return JSONResponse(error_body(exc.code, exc.message, exc.details), status_code=status)

    @app.exception_handler(RequestValidationError)
    async def _invalid_request(_: Request, exc: RequestValidationError) -> JSONResponse:
        fields = sorted({".".join(str(p) for p in e["loc"]) for e in exc.errors()})
        return JSONResponse(
            error_body("invalid_request", "the request is not valid", {"fields": fields}),
            status_code=422,
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = _HTTP_CODES.get(exc.status_code, "http_error")
        return JSONResponse(
            error_body(code, str(exc.detail)),
            status_code=exc.status_code,
            headers=getattr(exc, "headers", None),
        )
