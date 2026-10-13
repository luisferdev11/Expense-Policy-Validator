"""Keep prompt cls-v2 in Langfuse Prompt Management so every generation can link it (C1).

Called once per run before the first billed call. A new version is created only when the stored
text or config under the label differs (ported from explorations/scripts/langfuse_log_e13.py).
A no-op with the no-op tracer; a failure only disables the link, never the run.
"""

from __future__ import annotations

import warnings
from typing import Any

from expense_validator.adapters.openrouter.classifier import ENDPOINT, MAX_TOKENS, MODEL_ID
from expense_validator.adapters.openrouter.decision_prompt import (
    DECISION_ENDPOINT_PATH,
    DECISION_INSTRUCTIONS,
    DECISION_MODEL_ID,
    DECISION_PROMPT_NAME,
    DECISION_PROMPT_VERSION,
    criteria,
)
from expense_validator.adapters.openrouter.prompt import PROMPT_NAME, PROMPT_VERSION, SCHEMA, SYSTEM
from expense_validator.adapters.tracing import GuardedTracer, LangfuseTracer, TracingWarning

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


def _sync(
    tracer: GuardedTracer,
    name: str,
    label: str,
    kind: str,
    prompt: Any,
    config: dict[str, Any],
    commit_message: str,
) -> Any:
    """Create the prompt under its label when the stored text or config differs; return the
    client's prompt object, or None when tracing is off or the sync failed."""
    inner = tracer.inner
    if not isinstance(inner, LangfuseTracer):
        return None
    client = inner.client
    try:
        try:
            current = client.get_prompt(name, label=label, type=kind, cache_ttl_seconds=0)
            if current.prompt == prompt and (current.config or {}) == config:
                return current
        except Exception:
            current = None
        client.create_prompt(
            name=name,
            type=kind,
            prompt=prompt,
            labels=[label],
            config=config,
            commit_message=commit_message,
        )
        return client.get_prompt(name, label=label, type=kind, cache_ttl_seconds=0)
    except Exception as exc:
        warnings.warn(
            f"could not sync prompt {name}/{label}: {type(exc).__name__}",
            TracingWarning,
            stacklevel=3,
        )
        return None


def sync_prompt(tracer: GuardedTracer) -> Any:
    """Return the Langfuse prompt client for cls-v2, or None when tracing is off."""
    return _sync(
        tracer,
        PROMPT_NAME,
        PROMPT_VERSION,
        "chat",
        CHAT_PROMPT,
        CONFIG,
        f"{PROMPT_VERSION}: category, subtype (A6), recipient fields (A9)",
    )


DECISION_TEXT = (
    DECISION_INSTRUCTIONS
    + "\n\nCriteria (option: typical examples):\n"
    + "\n".join(f"- {option}: {examples}" for option, examples in criteria().items())
    + "\n\nState: item={{description_clean}}, merchant={{merchant_name}}, mcc={{mcc}}"
)
DECISION_CONFIG: dict[str, Any] = {
    "model": DECISION_MODEL_ID,
    "endpoint": DECISION_ENDPOINT_PATH,
    "kind": "decision",
}


def sync_decision_prompt(tracer: GuardedTracer) -> Any:
    """Return the Langfuse prompt client for dec-v1 (`classify-item-decision`), or None."""
    return _sync(
        tracer,
        DECISION_PROMPT_NAME,
        DECISION_PROMPT_VERSION,
        "text",
        DECISION_TEXT,
        DECISION_CONFIG,
        f"{DECISION_PROMPT_VERSION}: decision payload moved into the package (category only)",
    )
