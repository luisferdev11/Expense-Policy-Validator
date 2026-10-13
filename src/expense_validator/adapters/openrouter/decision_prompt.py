"""Prompt dec-v1 for a decision model (jev) and its strict parser (spec 007, FR-002, FR-004).

Moved from explorations/lib/decision_adapters.py so package code never imports research code. The
instructions and the shape of `decision_payload` are the ones E13 and the 2026-10-11 jev run sent;
`tests/fixtures/dec_v1_payload.json`, captured once from the exploration code, pins that the moved
payload is the same for three items, so the dev-set evidence stays valid.

A decision model answers with a choice and a probability distribution through
POST /api/alpha/decisions (OpenRouter's jev tutorial): `state` holds the input, `questions` maps an
id to `{type: "choice", instructions, criteria}`. Questions are answered in isolation, so all the
meaning goes in the instructions and the criteria. It returns a category only: no subtype and no
recipient.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Literal, cast

from expense_validator.adapters.openrouter.prompt import EXAMPLES, ParseError
from expense_validator.domain.models import ClassifierRequest
from expense_validator.domain.taxonomy import CATEGORIES, Category

DECISION_PROMPT_VERSION = "dec-v1"
DECISION_PROMPT_NAME = "classify-item-decision"
DECISION_MODEL_ID = "typesafe/jev-1.13"
DECISION_ENDPOINT_PATH = "/api/alpha/decisions"

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

ConfidenceSource = Literal["top_probability", "confidence"]


def criteria() -> dict[str, str]:
    """Each option and its typical examples, from the package taxonomy."""
    return {c: EXAMPLES[c] for c in CATEGORIES}


def decision_payload(request: ClassifierRequest) -> dict[str, Any]:
    """The request body after `model`: the item, the merchant and the closed set of options."""
    return {
        "state": {
            "item": request.description_clean,
            "merchant": request.merchant_name,
            "mcc": str(request.mcc),
        },
        "questions": {
            "category": {
                "type": "choice",
                "instructions": DECISION_INSTRUCTIONS,
                "criteria": criteria(),
            }
        },
    }


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def decision_cache_key(request: ClassifierRequest, model_id: str, endpoint: str) -> str:
    """The `cache_key` family of the chat classifier, extended with the payload's digest because
    the decision payload carries the instructions and the criteria. It can never equal a `cls-v2`
    key: the prompt version differs."""
    digest = hashlib.sha256(_canonical(decision_payload(request)).encode("utf-8")).hexdigest()
    canonical = _canonical(
        {
            "description_clean": request.description_clean,
            "merchant_name": request.merchant_name,
            "mcc": request.mcc,
            "model_id": model_id,
            "provider_endpoint": endpoint,
            "prompt_version": DECISION_PROMPT_VERSION,
            "payload_digest": digest,
        }
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class DecisionAnswer:
    category: Category
    confidence: float
    confidence_source: ConfidenceSource


def _unit_interval(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value) if 0 <= value <= 1 else None


def parse_decision(content: str | None) -> DecisionAnswer:
    """Strict parse of the literal response body.

    The category is `answers.category.choice`, one of the 21. The confidence is the top
    probability (`probabilities[choice]`) when present and in [0, 1], else `confidence` when in
    [0, 1]; with neither the answer is a schema violation.
    """
    try:
        body = json.loads(content or "")
    except json.JSONDecodeError as exc:
        raise ParseError(f"invalid JSON: {exc.msg}") from None
    answers = body.get("answers") if isinstance(body, dict) else None
    answer = answers.get("category") if isinstance(answers, dict) else None
    if not isinstance(answer, dict):
        raise ParseError("answers.category is missing")
    choice = answer.get("choice")
    if choice not in CATEGORIES:
        raise ParseError(f"choice not in taxonomy: {choice!r}")
    probabilities = answer.get("probabilities")
    top = _unit_interval(probabilities.get(choice)) if isinstance(probabilities, dict) else None
    if top is not None:
        return DecisionAnswer(cast(Category, choice), top, "top_probability")
    reported = _unit_interval(answer.get("confidence"))
    if reported is None:
        raise ParseError("no usable confidence in [0, 1]")
    return DecisionAnswer(cast(Category, choice), reported, "confidence")
