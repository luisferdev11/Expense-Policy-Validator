"""One interface for every item classifier we compare, all through OpenRouter.

Two kinds of backend:

- `ChatJSONClassifier`: a generative model asked for a strict JSON answer (category plus a
  self-reported confidence), with prompt `cls-v1` from `classifier_prompt.py`.
- `DecisionClassifier`: a decision model (for example jev, GPT-6 Luna Decisions, Clef) called
  through POST /api/alpha/decisions. It returns a choice and a probability distribution over the
  options instead of generated text. Prompt version `dec-v1`.

Both return a `Prediction`. The decision request shape follows OpenRouter's jev tutorial
(https://openrouter.ai/docs/guides/community/jev-tutorial, fetched 2026-10-08): `state`
holds the input and `questions` maps an id to `{type: "choice", instructions, criteria}`, where
`criteria` maps each option to its description. The answer has `choice`, `probabilities` and
`confidence`. Questions are answered in isolation, so all meaning goes in the instructions and
the criteria.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

EXP = Path(__file__).resolve().parent.parent  # explorations/
sys.path.insert(0, str(EXP / "lib"))
import budget
import classifier_prompt as cp

DECISION_PROMPT_VERSION = "dec-v1"


@dataclass
class Prediction:
    category: str | None
    confidence: float | None = None
    probabilities: dict[str, float] | None = None
    request_id: str | None = None
    latency_s: float | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    cached: bool = False
    schema_valid: bool | None = None
    error: str | None = None
    finish_reason: str | None = None
    served_by: str | None = None


class ItemClassifier(Protocol):
    model: str

    def classify(self, item: dict[str, Any]) -> Prediction: ...


@dataclass
class ChatJSONClassifier:
    model: str
    reasoning_effort: str | None = "low"
    extra_body: dict[str, Any] | None = None
    # Part of the cache key: a variant with different call settings must not reuse another
    # variant's cached answers.
    prompt_tag: str = cp.PROMPT_VERSION

    def classify(self, item: dict[str, Any]) -> Prediction:
        res = budget.call(
            "openrouter",
            self.model,
            cp.messages(item),
            prompt_version=self.prompt_tag,
            cache_input=cp.cache_input(item),
            response_format=cp.RESPONSE_FORMAT_STRICT,
            max_tokens=1024,
            reasoning_effort=self.reasoning_effort,
            extra_body=self.extra_body,
            purpose="trial",
        )
        cat, conf, err = cp.parse(res["content"])
        return Prediction(
            cat,
            conf,
            None,
            res["request_id"],
            res["latency_s"],
            res["prompt_tokens"],
            res["completion_tokens"],
            res["cached"],
            cp.schema_valid(res["content"]),
            err,
            res.get("finish_reason"),
            res.get("served_by"),
        )


DECISION_INSTRUCTIONS = (
    "Choose the spend category of one line item from an expense receipt. The state gives the "
    "item text exactly as printed (it may be in English, Spanish, French, German, Portuguese or "
    "Japanese), the merchant name and the merchant category code (MCC). "
    "Classify what the item IS, not the words in its name: food cooked with alcohol (beer-battered "
    "fish, rum cake, wine sauce) is food_beverage; non-alcoholic drinks and mocktails are "
    "food_beverage; cooking wine is alcohol; barware and drinkware are household_goods. "
    "Accessories made for a personal device (cases, chargers) are personal_electronics; "
    "non-electronic watches are jewelry. Mobile phones, prescription medication and event "
    "tickets have no category of their own: choose other. A charge with unknown contents is other."
)


def decision_payload(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "state": {
            "item": item["description"],
            "merchant": item["merchant_name"],
            "mcc": str(item["mcc"]),
        },
        "questions": {
            "category": {
                "type": "choice",
                "instructions": DECISION_INSTRUCTIONS,
                "criteria": {c: ex for c, (_, ex) in cp.TAXONOMY.items()},
            }
        },
    }


@dataclass
class DecisionClassifier:
    model: str

    def classify(self, item: dict[str, Any]) -> Prediction:
        res = budget.call_decision(
            self.model,
            decision_payload(item),
            prompt_version=DECISION_PROMPT_VERSION,
            cache_input=cp.cache_input(item),
            purpose="trial",
        )
        ans = (res["body"].get("answers") or {}).get("category") or {}
        choice = ans.get("choice")
        probs = ans.get("probabilities") if isinstance(ans.get("probabilities"), dict) else None
        valid = choice in cp.TAXONOMY
        return Prediction(
            choice if valid else None,
            ans.get("confidence"),
            probs,
            res["request_id"],
            res["latency_s"],
            res["prompt_tokens"],
            res["completion_tokens"],
            res["cached"],
            valid,
            None if valid else f"choice not in taxonomy: {choice!r}",
            None,
            res.get("served_by"),
        )


def make_classifier(model: str, kind: str) -> ItemClassifier:
    if kind == "decision":
        return DecisionClassifier(model)
    if kind == "chat":
        return ChatJSONClassifier(model)
    raise ValueError(f"unknown kind {kind!r}")
