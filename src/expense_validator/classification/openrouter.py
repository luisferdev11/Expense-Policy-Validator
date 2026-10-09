"""OpenRouter adapter for the ItemClassifier port (research R3, FR-025, FR-026).

Ported from explorations/lib/budget.py: one pinned endpoint with no fallbacks, temperature 0,
low reasoning effort, the strict cls-v2 schema, billed cost read from `usage.cost`, and a spend
cap checked before every billed call. Every billed call is one `classify-item` generation; a
cache hit is not a call and produces none. The key is read from the environment and never
logged.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

from expense_validator.classification.cache import ClassificationCache, cache_key
from expense_validator.classification.prompt import (
    PROMPT_VERSION,
    RESPONSE_FORMAT_STRICT,
    ParseError,
    messages,
    parse,
)
from expense_validator.classification.taxonomy import restricted_for
from expense_validator.models import (
    CacheEntry,
    Classification,
    ClassificationSource,
    ClassifierRequest,
)
from expense_validator.paths import RAW_CACHE_DIR
from expense_validator.tracing import Tracer

MODEL_ID = "openai/gpt-oss-120b"
ENDPOINT = "deepinfra/bf16"
BASE_URL = "https://openrouter.ai/api/v1"
CAP_USD = 1.00
MAX_TOKENS = 1024
REASONING_EFFORT = "low"
KEY_ENV = "OPENROUTER_API_KEY"
PIN: dict[str, Any] = {
    "order": [ENDPOINT],
    "allow_fallbacks": False,
    "require_parameters": True,
    "data_collection": "deny",
}

Transport = Callable[[dict[str, Any]], tuple[dict[str, Any], str]]


def openai_transport(api_key: str) -> Transport:
    """Real transport: the OpenAI SDK pointed at OpenRouter. Returns (body, body_text)."""
    from openai import OpenAI

    client = OpenAI(
        base_url=BASE_URL,
        api_key=api_key,
        max_retries=2,
        timeout=120,
        default_headers={"User-Agent": "expense-policy-validator/0.1"},
    )

    def send(payload: dict[str, Any]) -> tuple[dict[str, Any], str]:
        completion = client.chat.completions.create(**payload)
        body: dict[str, Any] = completion.model_dump(mode="json")
        return body, json.dumps(body, ensure_ascii=False)

    return send


def _safe(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", name)


class OpenRouterClassifier:
    name = "openrouter"
    model_id = MODEL_ID
    provider_endpoint = ENDPOINT
    prompt_version = PROMPT_VERSION

    def __init__(
        self,
        cache: ClassificationCache,
        tracer: Tracer,
        transport: Transport | None = None,
        offline: bool = False,
        cap_usd: float = CAP_USD,
        raw_dir: Path = RAW_CACHE_DIR,
        prompt_link: Any = None,
    ) -> None:
        self.cache = cache
        self.tracer = tracer
        self.offline = offline
        self.cap_usd = cap_usd
        self.raw_dir = raw_dir
        self.prompt_link = prompt_link
        self._transport = transport
        self.calls_made = 0
        self.cache_hits = 0
        self.run_spend_usd = 0.0

    def _get_transport(self) -> Transport:
        if self._transport is None:
            key = os.environ.get(KEY_ENV)
            if not key:
                raise RuntimeError(f"{KEY_ENV} is not set")
            self._transport = openai_transport(key)
        return self._transport

    def payload(self, request: ClassifierRequest) -> dict[str, Any]:
        return {
            "model": MODEL_ID,
            "messages": messages(request),
            "max_tokens": MAX_TOKENS,
            "temperature": 0,
            "response_format": RESPONSE_FORMAT_STRICT,
            "extra_body": {"provider": PIN, "reasoning": {"effort": REASONING_EFFORT}},
        }

    def _source(self, key: str, entry: CacheEntry | None, cache_hit: bool) -> ClassificationSource:
        return ClassificationSource(
            classifier=self.name,
            model_id=MODEL_ID,
            provider_endpoint=ENDPOINT,
            prompt_version=PROMPT_VERSION,
            cache_key=key,
            request_id=entry.request_id if entry else None,
            cost_usd=entry.cost_usd if entry else None,
            prompt_tokens=entry.prompt_tokens if entry else None,
            completion_tokens=entry.completion_tokens if entry else None,
            cache_hit=cache_hit,
        )

    def _unclassified(self, line_id: str, key: str, reason: str) -> Classification:
        return Classification(
            line_id=line_id,
            status="unclassified",
            category=None,
            restricted=None,
            confidence=None,
            unclassified_reason=reason,
            source=self._source(key, None, cache_hit=False),
        )

    def _from_entry(self, line_id: str, entry: CacheEntry, cache_hit: bool) -> Classification:
        """Parse the cached raw answer; a schema violation stays one on every replay."""
        try:
            answer = parse(entry.content)
        except ParseError:
            return Classification(
                line_id=line_id,
                status="unclassified",
                category=None,
                restricted=None,
                confidence=None,
                unclassified_reason="schema_violation",
                source=self._source(entry.cache_key, entry, cache_hit),
            )
        return Classification(
            line_id=line_id,
            status="classified",
            category=answer.category,
            restricted=restricted_for(answer.category),
            confidence=answer.confidence,
            subtype=answer.subtype,
            recipient_kind=answer.recipient_kind,
            recipient_name=answer.recipient_name,
            source=self._source(entry.cache_key, entry, cache_hit),
        )

    def classify(self, line_id: str, request: ClassifierRequest) -> Classification:
        key = cache_key(request, MODEL_ID, ENDPOINT, PROMPT_VERSION)
        hit = self.cache.get(key)
        if hit is not None:
            self.cache_hits += 1
            return self._from_entry(line_id, hit, cache_hit=True)
        if self.offline:
            return self._unclassified(line_id, key, "offline_cache_miss")
        if self.cache.total_cost_usd() >= self.cap_usd:
            return self._unclassified(line_id, key, "budget_refused")
        return self._call(line_id, request, key)

    def _call(self, line_id: str, request: ClassifierRequest, key: str) -> Classification:
        payload = self.payload(request)
        with self.tracer.generation(
            "classify-item",
            model=MODEL_ID,
            input=payload["messages"],
            model_parameters={
                "temperature": 0,
                "max_tokens": MAX_TOKENS,
                "reasoning_effort": REASONING_EFFORT,
                "provider_endpoint": ENDPOINT,
            },
            prompt=self.prompt_link,
            metadata={"prompt_version": PROMPT_VERSION, "cache_key": key},
        ) as generation:
            try:
                body, text = self._get_transport()(payload)
            except Exception as exc:
                generation.update(level="ERROR", status_message=type(exc).__name__)
                return self._unclassified(line_id, key, "gateway_error")
            self.calls_made += 1
            choice = (body.get("choices") or [{}])[0]
            message = choice.get("message") or {}
            content = message.get("content")
            reasoning = message.get("reasoning")
            usage = body.get("usage") or {}
            prompt_tokens = int(usage.get("prompt_tokens") or 0)
            completion_tokens = int(usage.get("completion_tokens") or 0)
            cost = usage.get("cost")
            cost_usd = float(cost) if cost is not None else None
            request_id = str(body.get("id") or f"noid-{key[:16]}")
            self.run_spend_usd += cost_usd or 0.0
            self.raw_dir.mkdir(parents=True, exist_ok=True)
            (self.raw_dir / f"{_safe(request_id)}.json").write_text(text, encoding="utf-8")
            generation.update(
                output=content,
                usage_details={"input": prompt_tokens, "output": completion_tokens},
                cost_details={"total": cost_usd or 0.0},
                metadata={
                    "request_id": request_id,
                    "reasoning": reasoning,
                    "served_by": body.get("provider"),
                    "finish_reason": choice.get("finish_reason"),
                },
            )
            try:
                parse(content)
            except ParseError as exc:
                generation.update(level="WARNING", status_message=f"schema_violation: {exc}")
        entry = CacheEntry(
            cache_key=key,
            content=content,
            model_id=MODEL_ID,
            provider_endpoint=ENDPOINT,
            prompt_version=PROMPT_VERSION,
            request_id=request_id,
            cost_usd=cost_usd,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            reasoning=reasoning,
        )
        self.cache.put(entry)
        return self._from_entry(line_id, entry, cache_hit=False)
