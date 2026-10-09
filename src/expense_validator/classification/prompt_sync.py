"""Keep prompt cls-v2 in Langfuse Prompt Management so every generation can link it (C1).

Called once per run before the first billed call. A new version is created only when the stored
text or config under the label differs (ported from explorations/scripts/langfuse_log_e13.py).
A no-op with the no-op tracer; a failure only disables the link, never the run.
"""

from __future__ import annotations

import warnings
from typing import Any

from expense_validator.classification.openrouter import ENDPOINT, MAX_TOKENS, MODEL_ID
from expense_validator.classification.prompt import PROMPT_NAME, PROMPT_VERSION, SCHEMA, SYSTEM
from expense_validator.tracing import GuardedTracer, LangfuseTracer, TracingWarning

USER_TEMPLATE = "Item: {{description_clean}}\nMerchant: {{merchant_name}}\nMCC: {{mcc}}"
CHAT_PROMPT = [
    {"role": "system", "content": SYSTEM},
    {"role": "user", "content": USER_TEMPLATE},
]
CONFIG: dict[str, Any] = {
    "model": MODEL_ID,
    "provider_endpoint": ENDPOINT,
    "temperature": 0,
    "max_tokens": MAX_TOKENS,
    "response_schema": SCHEMA,
}


def sync_prompt(tracer: GuardedTracer) -> Any:
    """Return the Langfuse prompt client for cls-v2, or None when tracing is off."""
    inner = tracer.inner
    if not isinstance(inner, LangfuseTracer):
        return None
    client = inner.client
    try:
        try:
            current = client.get_prompt(
                PROMPT_NAME, label=PROMPT_VERSION, type="chat", cache_ttl_seconds=0
            )
            if current.prompt == CHAT_PROMPT and (current.config or {}) == CONFIG:
                return current
        except Exception:
            current = None
        client.create_prompt(
            name=PROMPT_NAME,
            type="chat",
            prompt=CHAT_PROMPT,
            labels=[PROMPT_VERSION],
            config=CONFIG,
            commit_message=f"{PROMPT_VERSION}: category, subtype (A6), recipient fields (A9)",
        )
        return client.get_prompt(
            PROMPT_NAME, label=PROMPT_VERSION, type="chat", cache_ttl_seconds=0
        )
    except Exception as exc:
        warnings.warn(
            f"could not sync prompt {PROMPT_NAME}/{PROMPT_VERSION}: {type(exc).__name__}",
            TracingWarning,
            stacklevel=2,
        )
        return None
