"""A decision model (jev) behind the ItemClassifier port (spec 007, FR-001 to FR-009).

POST https://openrouter.ai/api/alpha/decisions with the `dec-v1` payload. The model answers with a
category and a probability distribution, so a classification from it has category and confidence
and nothing else: subtype `none`, recipient `none` (the hybrid fills those from a chat model).

Like the chat adapter, a billed call is one `classify-item` generation, a cache hit is none, the
literal response is cached before it is parsed (so a schema violation replays identically), and a
spend cap is checked before every billed call. The cap counts what this process billed; cached
and seeded answers never count. The key is read from the environment and never logged.
"""

from __future__ import annotations

import json
import os
import re
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx

from expense_validator.adapters.openrouter.decision_prompt import (
    DECISION_ENDPOINT_PATH,
    DECISION_MODEL_ID,
    DECISION_PROMPT_VERSION,
    decision_cache_key,
    decision_payload,
    parse_decision,
)
from expense_validator.adapters.openrouter.models import ROUTED
from expense_validator.adapters.openrouter.prompt import ParseError
from expense_validator.domain.models import (
    CacheEntry,
    Classification,
    ClassificationSource,
    ClassifierRequest,
)
from expense_validator.domain.taxonomy import restricted_for
from expense_validator.paths import RAW_CACHE_DIR
from expense_validator.ports.classification_cache import ClassificationCachePort
from expense_validator.ports.tracer import Tracer

URL = "https://openrouter.ai/api/alpha/decisions"
CAP_USD = 1.00
KEY_ENV = "OPENROUTER_API_KEY"
TIMEOUT_S = 120.0
MAX_ATTEMPTS = 6
RETRY_STATUSES = (429, 502, 503)

Transport = Callable[[dict[str, Any]], tuple[dict[str, Any], str]]


def httpx_transport(
    api_key: str,
    client: httpx.Client | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> Transport:
    """Real transport. Retries 429, 502 and 503 with backoff `min(30, 2**attempt)` seconds, up to
    six attempts in all; any other status of 400 or above raises. Never logs the key."""
    http = client or httpx.Client(timeout=TIMEOUT_S)
    headers = {
        "Authorization": f"Bearer {api_key}",
        "User-Agent": "expense-policy-validator/1.2",
    }

    def send(payload: dict[str, Any]) -> tuple[dict[str, Any], str]:
        for attempt in range(1, MAX_ATTEMPTS + 1):
            response = http.post(URL, json=payload, headers=headers)
            if response.status_code < 400:
                text = response.text
                body: dict[str, Any] = json.loads(text)
                return body, text
            if response.status_code in RETRY_STATUSES and attempt < MAX_ATTEMPTS:
                sleep(min(30, 2**attempt))
                continue
            raise RuntimeError(f"HTTP {response.status_code} from the decisions endpoint")
        raise RuntimeError("unreachable")

    return send


def _safe(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", name)


class DecisionClassifier:
    name = "openrouter-decision"
    model_id = DECISION_MODEL_ID
    provider_endpoint = ROUTED
    prompt_version = DECISION_PROMPT_VERSION

    def __init__(
        self,
        cache: ClassificationCachePort,
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
        self.last_latency_s: float | None = None  # of the last billed call; None after a hit

    def _get_transport(self) -> Transport:
        if self._transport is None:
            key = os.environ.get(KEY_ENV)
            if not key:
                raise RuntimeError(f"{KEY_ENV} is not set")
            self._transport = httpx_transport(key)
        return self._transport

    def _source(self, key: str, entry: CacheEntry | None, cache_hit: bool) -> ClassificationSource:
        return ClassificationSource(
            classifier=self.name,
            model_id=self.model_id,
            provider_endpoint=self.provider_endpoint,
            prompt_version=self.prompt_version,
            cache_key=key,
            request_id=entry.request_id if entry else None,
            cost_usd=entry.cost_usd if entry else None,
            prompt_tokens=entry.prompt_tokens if entry else None,
            completion_tokens=entry.completion_tokens if entry else None,
            cache_hit=cache_hit,
            served_by=entry.served_by if entry else None,
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
        """Parse the cached literal body; a schema violation stays one on every replay."""
        try:
            answer = parse_decision(entry.content)
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
            source=self._source(entry.cache_key, entry, cache_hit),
        )

    def classify(self, line_id: str, request: ClassifierRequest) -> Classification:
        key = decision_cache_key(request, self.model_id, self.provider_endpoint)
        self.last_latency_s = None
        hit = self.cache.get(key)
        if hit is not None:
            self.cache_hits += 1
            return self._from_entry(line_id, hit, cache_hit=True)
        if self.offline:
            return self._unclassified(line_id, key, "offline_cache_miss")
        if self.run_spend_usd >= self.cap_usd:
            return self._unclassified(line_id, key, "budget_refused")
        return self._call(line_id, request, key)

    def _call(self, line_id: str, request: ClassifierRequest, key: str) -> Classification:
        payload = decision_payload(request)
        with self.tracer.generation(
            "classify-item",
            model=self.model_id,
            input=payload,
            model_parameters={
                "endpoint": DECISION_ENDPOINT_PATH,
                "kind": "decision",
                "provider_endpoint": self.provider_endpoint,
            },
            prompt=self.prompt_link,
            metadata={"prompt_version": self.prompt_version, "cache_key": key},
        ) as generation:
            started = time.monotonic()
            try:
                body, text = self._get_transport()({"model": self.model_id, **payload})
            except Exception as exc:
                generation.update(level="ERROR", status_message=type(exc).__name__)
                return self._unclassified(line_id, key, "gateway_error")
            self.last_latency_s = round(time.monotonic() - started, 3)
            self.calls_made += 1
            usage = body.get("usage") or {}
            prompt_tokens = int(usage.get("input_tokens", usage.get("prompt_tokens", 0)) or 0)
            completion_tokens = int(
                usage.get("output_tokens", usage.get("completion_tokens", 0)) or 0
            )
            cost = usage.get("cost")
            cost_usd = float(cost) if cost is not None else None
            request_id = str(body.get("id") or f"noid-{key[:16]}")
            self.run_spend_usd += cost_usd or 0.0
            self.raw_dir.mkdir(parents=True, exist_ok=True)
            (self.raw_dir / f"{_safe(request_id)}.json").write_text(text, encoding="utf-8")
            source = "none"
            violation: str | None = None
            try:
                source = parse_decision(text).confidence_source
            except ParseError as exc:
                violation = f"schema_violation: {exc}"
            answers = body.get("answers")
            generation.update(
                output=answers.get("category") if isinstance(answers, dict) else None,
                usage_details={"input": prompt_tokens, "output": completion_tokens},
                cost_details={"total": cost_usd or 0.0},
                metadata={
                    "request_id": request_id,
                    "served_by": body.get("provider"),
                    "confidence_source": source,
                },
            )
            if violation is not None:
                generation.update(level="WARNING", status_message=violation)
        entry = CacheEntry(
            cache_key=key,
            content=text,
            model_id=self.model_id,
            provider_endpoint=self.provider_endpoint,
            prompt_version=self.prompt_version,
            request_id=request_id,
            cost_usd=cost_usd,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            reasoning=f"confidence_source={source}",
            served_by=body.get("provider"),
        )
        if self.cache.put(entry):
            return self._from_entry(line_id, entry, cache_hit=False)
        # Another worker stored this key while the call was in flight: its row wins, so every
        # receipt sees the same answer. This call was billed and is counted in `calls_made`.
        stored = self.cache.get(key)
        return self._from_entry(line_id, stored if stored is not None else entry, cache_hit=True)
