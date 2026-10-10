"""Translator for experiment E5 (research R6): an expense line to English, with prompt tr-v1.

Uses the reference pin, temperature 0, a cache of literal translations and one `translate-item`
generation per billed call. English text is never sent. A failure returns None and the caller
falls back to the original text, so translation never blocks classification. If E5 does not win,
no Translator port is added to the pipeline (constitution XI).
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

from expense_validator.adapters.openrouter.classifier import (
    KEY_ENV,
    Transport,
    openai_transport,
    provider,
)
from expense_validator.adapters.openrouter.models import REFERENCE, ModelPin
from expense_validator.paths import RAW_CACHE_DIR
from expense_validator.ports.tracer import Tracer

PROMPT_VERSION = "tr-v1"
SYSTEM = (
    "Translate this line from an expense receipt into English. Keep product names, brands, "
    "quantities and units. Do not explain or classify it. Output only the translation."
)


class Translator:
    def __init__(
        self,
        cache_path: Path,
        tracer: Tracer,
        transport: Transport | None = None,
        offline: bool = False,
        raw_dir: Path = RAW_CACHE_DIR,
        pin: ModelPin = REFERENCE,
    ) -> None:
        self.cache_path = cache_path
        self.tracer = tracer
        self.offline = offline
        self.raw_dir = raw_dir
        self.pin = pin
        self._transport = transport
        self.calls_made = 0
        self.run_spend_usd = 0.0
        self._rows: dict[str, dict[str, Any]] = {}
        if cache_path.exists():
            for line in cache_path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    row = json.loads(line)
                    self._rows[row["key"]] = row

    def _key(self, text: str, language: str) -> str:
        canonical = json.dumps(
            [text, language, self.pin.model_id, self.pin.endpoint, PROMPT_VERSION],
            ensure_ascii=False,
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def translate(self, text: str, language: str) -> str | None:
        if language == "en":
            return text
        key = self._key(text, language)
        if key in self._rows:
            translation: str | None = self._rows[key]["translation"]
            return translation
        if self.offline:
            return None
        return self._call(text, language, key)

    def _call(self, text: str, language: str, key: str) -> str | None:
        messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": text}]
        payload = {
            "model": self.pin.model_id,
            "messages": messages,
            "max_tokens": 512,
            "temperature": 0,
            "extra_body": {"provider": provider(self.pin), **self.pin.extra_reasoning()},
        }
        with self.tracer.generation(
            "translate-item",
            model=self.pin.model_id,
            input=messages,
            metadata={"prompt_version": PROMPT_VERSION, "language": language, "cache_key": key},
        ) as generation:
            try:
                if self._transport is None:
                    api_key = os.environ.get(KEY_ENV)
                    if not api_key:
                        raise RuntimeError(f"{KEY_ENV} is not set")
                    self._transport = openai_transport(api_key)
                body, raw = self._transport(payload)
            except Exception as exc:
                generation.update(level="ERROR", status_message=type(exc).__name__)
                return None
            self.calls_made += 1
            message = ((body.get("choices") or [{}])[0]).get("message") or {}
            content = (message.get("content") or "").strip() or None
            usage = body.get("usage") or {}
            cost = float(usage["cost"]) if usage.get("cost") is not None else None
            self.run_spend_usd += cost or 0.0
            request_id = str(body.get("id") or f"noid-{key[:16]}")
            self.raw_dir.mkdir(parents=True, exist_ok=True)
            (self.raw_dir / f"{request_id}.json").write_text(raw, encoding="utf-8")
            generation.update(
                output=content,
                usage_details={
                    "input": int(usage.get("prompt_tokens") or 0),
                    "output": int(usage.get("completion_tokens") or 0),
                },
                cost_details={"total": cost or 0.0},
                metadata={"request_id": request_id},
            )
        self._rows[key] = {
            "key": key,
            "text": text,
            "language": language,
            "translation": content,
            "model_id": self.pin.model_id,
            "prompt_version": PROMPT_VERSION,
            "request_id": request_id,
            "cost_usd": cost,
        }
        return content

    def total_cost_usd(self) -> float:
        return sum(row.get("cost_usd") or 0.0 for row in self._rows.values())

    def save(self) -> None:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        lines = [json.dumps(self._rows[k], ensure_ascii=False) for k in sorted(self._rows)]
        self.cache_path.write_text("".join(line + "\n" for line in lines), encoding="utf-8")
