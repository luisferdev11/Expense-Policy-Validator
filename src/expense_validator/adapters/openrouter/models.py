"""The E14 candidates on OpenRouter (research R1, ADR 0004).

Each pin fixes the model and its reasoning setting. Routing is OpenRouter's own, with fallbacks
(Luis, 2026-10-09, after the pinned DeepInfra endpoint rate-limited Gemma); the provider that
served each call is recorded instead. Qwen runs with reasoning off, as in E13's declared
deviation, and Gemma takes no reasoning parameter.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ModelPin:
    name: str
    model_id: str
    endpoint: str  # always ROUTED; part of every cache key
    reasoning: dict[str, Any] | None

    def extra_reasoning(self) -> dict[str, Any]:
        return {} if self.reasoning is None else {"reasoning": self.reasoning}


ROUTED = "openrouter"

PINS: dict[str, ModelPin] = {
    "gpt-oss-120b": ModelPin("gpt-oss-120b", "openai/gpt-oss-120b", ROUTED, {"effort": "low"}),
    "gpt-oss-20b": ModelPin("gpt-oss-20b", "openai/gpt-oss-20b", ROUTED, {"effort": "low"}),
    "qwen3.5-9b": ModelPin("qwen3.5-9b", "qwen/qwen3.5-9b", ROUTED, {"enabled": False}),
    "gemma-3-12b": ModelPin("gemma-3-12b", "google/gemma-3-12b-it", ROUTED, None),
}
REFERENCE = PINS["gpt-oss-120b"]

# The names `classifier_model` and the factory accept: the chat pins above, a decision model
# (jev, category only) and the hybrid (jev's category with the reference's subtype and recipient).
JEV = "jev-1.13"
HYBRID = "jev-hybrid"
CLASSIFIER_NAMES: tuple[str, ...] = (*PINS, JEV, HYBRID)
