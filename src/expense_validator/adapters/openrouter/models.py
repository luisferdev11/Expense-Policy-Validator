"""Pinned OpenRouter endpoints for the E14 candidates (research R1).

Each pin fixes the model, one provider endpoint (no fallbacks) and the reasoning setting the
endpoint accepts. The pins come from explorations/research/openrouter_pins.json (E13); Qwen runs
with reasoning off, as in E13's declared deviation, and Gemma's endpoint has no reasoning
parameter.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ModelPin:
    name: str
    model_id: str
    endpoint: str
    reasoning: dict[str, Any] | None

    def extra_reasoning(self) -> dict[str, Any]:
        return {} if self.reasoning is None else {"reasoning": self.reasoning}


PINS: dict[str, ModelPin] = {
    "gpt-oss-120b": ModelPin(
        "gpt-oss-120b", "openai/gpt-oss-120b", "deepinfra/bf16", {"effort": "low"}
    ),
    "gpt-oss-20b": ModelPin(
        "gpt-oss-20b", "openai/gpt-oss-20b", "deepinfra/bf16", {"effort": "low"}
    ),
    "qwen3.5-9b": ModelPin("qwen3.5-9b", "qwen/qwen3.5-9b", "deepinfra/bf16", {"enabled": False}),
    "gemma-3-12b": ModelPin("gemma-3-12b", "google/gemma-3-12b-it", "deepinfra/bf16", None),
}
REFERENCE = PINS["gpt-oss-120b"]
