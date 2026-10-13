"""Classifiers for load tests: a fixed answer, and a wrapper that adds a sleep (research R13).

The committed answer cache holds only the lines of the 32 receipts, so generated receipts would
miss it. `SimulatedClassifier` answers every line the same way with no model call, which measures
the API, the store and the worker; `LatencyClassifier` reproduces the model's latency per line
(1 to 4 seconds in `docs/aws.md`) without paying for it. Neither is used outside load tests.
"""

from __future__ import annotations

import hashlib
import time
from collections.abc import Callable

from expense_validator.domain.models import Classification, ClassificationSource, ClassifierRequest
from expense_validator.domain.taxonomy import restricted_for
from expense_validator.ports.classifier import ItemClassifier

SIMULATED_VERSION = "sim-v1"
CATEGORY = "office_supplies"
CONFIDENCE = 0.99


class SimulatedClassifier:
    name = "simulated"
    model_id = "simulated"
    provider_endpoint = "none"
    prompt_version = SIMULATED_VERSION

    def __init__(self) -> None:
        self.calls_made = 0  # no model is ever called
        self.cache_hits = 0

    def classify(self, line_id: str, request: ClassifierRequest) -> Classification:
        key = hashlib.sha256(
            f"{SIMULATED_VERSION}|{request.description_clean}|{request.mcc}".encode()
        ).hexdigest()
        return Classification(
            line_id=line_id,
            status="classified",
            category=CATEGORY,
            restricted=restricted_for(CATEGORY),
            confidence=CONFIDENCE,
            source=ClassificationSource(
                classifier=self.name,
                model_id=self.model_id,
                provider_endpoint=self.provider_endpoint,
                prompt_version=self.prompt_version,
                cache_key=key,
                request_id=None,
                cost_usd=None,
                prompt_tokens=None,
                completion_tokens=None,
                cache_hit=False,
            ),
        )


class LatencyClassifier:
    """Sleeps `milliseconds` before every answer of `inner`, whichever classifier it is."""

    def __init__(
        self,
        inner: ItemClassifier,
        milliseconds: int,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._inner = inner
        self._seconds = milliseconds / 1000
        self._sleep = sleep
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

    def classify(self, line_id: str, request: ClassifierRequest) -> Classification:
        if self._seconds > 0:
            self._sleep(self._seconds)
        return self._inner.classify(line_id, request)
