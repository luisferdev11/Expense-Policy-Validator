"""A classifier wrapper that saves the answer cache right after every billed call.

The batch run saves once at the end. A worker can be killed at any line of a receipt, and a
billed answer that was never written would be paid for again on resume. Saving after each billed
call (and replacing the file atomically) makes "no extra billed call after a crash" true for the
real classifier, not only for a model of it.

The backend no longer uses it: its answer cache is a table written per row (spec 006), so every
billed answer is durable when it is stored. It stays for caches that are files.
"""

from __future__ import annotations

from collections.abc import Callable

from expense_validator.domain.models import Classification, ClassifierRequest
from expense_validator.ports.classifier import ItemClassifier


class PersistingClassifier:
    def __init__(self, inner: ItemClassifier, persist: Callable[[], None]) -> None:
        self._inner = inner
        self._persist = persist
        self.name = inner.name
        self.model_id = inner.model_id
        self.provider_endpoint = inner.provider_endpoint
        self.prompt_version = inner.prompt_version

    @property
    def calls_made(self) -> int:
        return int(getattr(self._inner, "calls_made", 0))

    @property
    def cache_hits(self) -> int:
        return int(getattr(self._inner, "cache_hits", 0))

    @property
    def last_flags(self) -> dict[str, bool]:
        """The hybrid's per-call trace flags, passed through; empty for any other classifier."""
        flags: dict[str, bool] = getattr(self._inner, "last_flags", {})
        return flags

    def classify(self, line_id: str, request: ClassifierRequest) -> Classification:
        before = self.calls_made
        result = self._inner.classify(line_id, request)
        if self.calls_made > before:
            self._persist()
        return result
