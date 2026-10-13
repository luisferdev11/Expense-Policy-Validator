"""Application errors. Each carries a stable code that the HTTP layer turns into a status."""

from __future__ import annotations

from typing import Any


class AppError(Exception):
    code = "error"

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class InvalidReceiptError(AppError):
    code = "invalid_receipt"


class InvalidIdempotencyKeyError(AppError):
    code = "invalid_idempotency_key"


class IdempotencyKeyReuseError(AppError):
    code = "idempotency_key_reuse"


class NotFoundError(AppError):
    code = "not_found"


class NoShadowError(AppError):
    """The receipt exists but its current revision has no shadow answers: shadow mode was off, or
    its work is still pending."""

    code = "no_shadow"


class ActionNotAllowedError(AppError):
    code = "action_not_allowed"


class StaleEvaluationError(AppError):
    code = "stale_evaluation"


class ReasonRequiredError(AppError):
    code = "reason_required"


class UnknownCategoryError(AppError):
    code = "unknown_category"


class InvalidActionError(AppError):
    code = "invalid_action"


class InvalidBatchError(AppError):
    code = "invalid_batch"
