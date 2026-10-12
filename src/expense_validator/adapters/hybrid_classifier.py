"""A hybrid ItemClassifier: jev's category and confidence, gpt-oss-120b's subtype and recipient.

jev classified 130 of 130 dev items on 2026-10-11 but returns no subtype and no recipient (A6, A9);
the chat model returns both. The hybrid asks both, the category side first, and merges them with the
table in `specs/007-jev-classifier/contracts/decision-adapter.md`. Each side keeps its own cache
entries under its own keys, its own spend cap and its own `classify-item` generations. The
`Classification` schema is unchanged: the merged source fields are composites joined with `+`.

Two flags are exposed after every call, for the `classify-receipt` span and nothing else:
`hybrid_conflict` (jev says `other` and the chat model does not) and `detail_violation` (the chat
model's answer broke its schema, so subtype and recipient fall back to `none`).
"""

from __future__ import annotations

import hashlib
from typing import Any

from expense_validator.adapters.classification_cache import ClassificationCache
from expense_validator.adapters.openrouter.classifier import OpenRouterClassifier
from expense_validator.adapters.openrouter.decision_classifier import DecisionClassifier
from expense_validator.adapters.openrouter.decision_prompt import DECISION_PROMPT_VERSION
from expense_validator.adapters.openrouter.models import ROUTED
from expense_validator.adapters.openrouter.prompt import PROMPT_VERSION
from expense_validator.domain.models import (
    Classification,
    ClassificationSource,
    ClassifierRequest,
)

TRANSIENT = ("gateway_error", "budget_refused")


def _joined(first: str | None, second: str | None) -> str | None:
    if first is None and second is None:
        return None
    if first is None or second is None:
        return first or second
    return f"{first}+{second}"


def _sum(first: int | float | None, second: int | float | None) -> Any:
    if first is None and second is None:
        return None
    return (first or 0) + (second or 0)


class HybridClassifier:
    name = "hybrid"
    provider_endpoint = ROUTED
    prompt_version = f"hyb-v1({DECISION_PROMPT_VERSION}+{PROMPT_VERSION})"

    def __init__(self, category_source: DecisionClassifier, detail_source: OpenRouterClassifier):
        self.category_source = category_source
        self.detail_source = detail_source
        self.model_id = f"{category_source.model_id}+{detail_source.model_id}"
        self.last_flags: dict[str, bool] = {}
        self.last_keys: tuple[str, str] | None = None
        self.last_latency_s: float | None = None  # the category side's; the detail side is cached

    @property
    def cache(self) -> ClassificationCache:
        """The detail side's cache; the factory gives both sides the same one."""
        cache = self.detail_source.cache
        assert isinstance(cache, ClassificationCache)
        return cache

    @property
    def calls_made(self) -> int:
        return self.category_source.calls_made + self.detail_source.calls_made

    @property
    def cache_hits(self) -> int:
        return self.category_source.cache_hits + self.detail_source.cache_hits

    @property
    def run_spend_usd(self) -> float:
        return self.category_source.run_spend_usd + self.detail_source.run_spend_usd

    def _source(self, category: Classification, detail: Classification) -> ClassificationSource:
        a, b = category.source, detail.source
        return ClassificationSource(
            classifier=self.name,
            model_id=self.model_id,
            provider_endpoint=self.provider_endpoint,
            prompt_version=self.prompt_version,
            cache_key=hashlib.sha256(f"{a.cache_key}+{b.cache_key}".encode()).hexdigest(),
            request_id=_joined(a.request_id, b.request_id),
            cost_usd=_sum(a.cost_usd, b.cost_usd),
            prompt_tokens=_sum(a.prompt_tokens, b.prompt_tokens),
            completion_tokens=_sum(a.completion_tokens, b.completion_tokens),
            cache_hit=a.cache_hit and b.cache_hit,
            served_by=_joined(a.served_by, b.served_by),
        )

    def _unclassified(
        self, line_id: str, category: Classification, detail: Classification, reason: str
    ) -> Classification:
        return Classification(
            line_id=line_id,
            status="unclassified",
            category=None,
            restricted=None,
            confidence=None,
            unclassified_reason=reason,
            source=self._source(category, detail),
        )

    def classify(self, line_id: str, request: ClassifierRequest) -> Classification:
        category = self.category_source.classify(line_id, request)
        detail = self.detail_source.classify(line_id, request)
        self.last_keys = (category.source.cache_key, detail.source.cache_key)
        self.last_latency_s = self.category_source.last_latency_s
        self.last_flags = {}
        source = self._source(category, detail)

        def merged(subtype: Any, kind: Any, name: str | None) -> Classification:
            return Classification(
                line_id=line_id,
                status="classified",
                category=category.category,
                restricted=category.restricted,
                confidence=category.confidence,
                subtype=subtype,
                recipient_kind=kind,
                recipient_name=name,
                source=source,
            )

        # The merge table, top to bottom: the first row that matches wins.
        if category.status == "classified" and detail.status == "classified":
            if category.category != "other":
                return merged("none", detail.recipient_kind, detail.recipient_name)
            if detail.category == "other":
                return merged(detail.subtype, detail.recipient_kind, detail.recipient_name)
            self.last_flags["hybrid_conflict"] = True
            return merged("none", detail.recipient_kind, detail.recipient_name)
        if category.status == "classified" and detail.unclassified_reason == "schema_violation":
            self.last_flags["detail_violation"] = True
            return merged("none", "none", None)
        if category.unclassified_reason == "schema_violation":
            return self._unclassified(line_id, category, detail, "schema_violation")
        if category.unclassified_reason in TRANSIENT:
            return self._unclassified(line_id, category, detail, str(category.unclassified_reason))
        if category.status == "classified" and detail.unclassified_reason in TRANSIENT:
            return self._unclassified(line_id, category, detail, str(detail.unclassified_reason))
        reasons = (category.unclassified_reason, detail.unclassified_reason)
        if "offline_cache_miss" in reasons:
            return self._unclassified(line_id, category, detail, "offline_cache_miss")
        # Not reachable with today's reasons; report whatever was given rather than mislabel it.
        return self._unclassified(line_id, category, detail, next(r for r in reasons if r))
