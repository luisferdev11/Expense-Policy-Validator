"""One interface for every item classifier we may want to compare.

Three kinds of backend:

- `ChatJSONClassifier`: an OpenAI-compatible chat model asked for strict JSON (what package 6
  ran: gpt-oss on Groq and DeepInfra, small DeepInfra models). Goes through `budget.call`.
- `OllamaJSONClassifier`: a local model through ollama with constrained JSON output.
- `DecisionClassifier`: a "decision model" that returns a choice plus a probability distribution
  instead of generated text (jev from TypeSafe, OpenAI's Decisions API, open-weight decision
  encoders). Goes through `budget.call_http`. Each endpoint is described by a `DecisionEndpoint`.

Every classifier returns a `Prediction` with the full probability distribution when the backend
gives one, so calibration (Brier, ECE, reliability) and the EXC-03 threshold can be compared
across backends on the same dev items.

STATUS: the decision endpoints are scaffolding. None has been called: there is no key for any of
them yet, and the request and response shapes below come from public docs or secondary articles
(see `verified` and `notes` on each endpoint). Run `--dry-run` to see the payloads without any
network call. Verify each shape against the provider's docs before the first real call.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

EXP = Path(__file__).resolve().parent
sys.path.insert(0, str(EXP))
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


class ItemClassifier(Protocol):
    provider: str
    model: str

    def classify(self, item: dict[str, Any]) -> Prediction: ...


# ------------------------------------------------------------------ chat models (what runs today)


@dataclass
class ChatJSONClassifier:
    provider: str
    model: str
    mode: str = "strict"  # "strict" json_schema, or "json_object" where json_schema is rejected
    extra_body: dict[str, Any] | None = None

    def classify(self, item: dict[str, Any]) -> Prediction:
        fmt = cp.RESPONSE_FORMAT_STRICT if self.mode == "strict" else {"type": "json_object"}
        res = budget.call(
            self.provider,
            self.model,
            cp.messages(item),
            prompt_version=cp.PROMPT_VERSION,
            cache_input=cp.cache_input(item),
            response_format=fmt,
            max_tokens=1024,
            reasoning_effort="low" if "gpt-oss" in self.model else None,
            extra_body=self.extra_body,
            purpose="classify",
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
        )


@dataclass
class OllamaJSONClassifier:
    model: str
    provider: str = "ollama"

    def classify(self, item: dict[str, Any]) -> Prediction:
        import run_trial

        res = run_trial.ollama_classify(self.model, item)
        cat, conf, err = cp.parse(res["content"])
        return Prediction(
            cat,
            conf,
            None,
            None,
            res["latency_s"],
            res.get("prompt_tokens"),
            res.get("completion_tokens"),
            res["cached"],
            cp.schema_valid(res["content"]),
            err,
        )


# ------------------------------------------------------------------ decision models (scaffolding)


def decision_instructions() -> str:
    """Category definitions and the taxonomy's "names lie" guidance, without the JSON-answer line
    (a decision model returns its choice natively)."""
    return cp.SYSTEM.rsplit("\nAnswer only with JSON", 1)[0]


def item_state(item: dict[str, Any]) -> str:
    return cp.user_message(item["description"], item["merchant_name"], item["mcc"])


@dataclass
class DecisionEndpoint:
    provider: str
    model: str
    url: str
    key_env: str
    build_payload: Callable[[dict[str, Any]], dict[str, Any]]
    parse: Callable[[dict[str, Any]], tuple[str | None, dict[str, float] | None, float | None]]
    verified: bool = False
    source_urls: list[str] = field(default_factory=list)
    notes: str = ""


# jev, native API. Request/response fields from https://docs.typesafe.ai/ and the quickstart
# (fetched 2026-10-07): POST /v1/systemone with `model`, `state` and `questions`, each question
# {type: noul|choice|score, instructions, criteria}; a choice answer has `choice`,
# `probabilities` and `confidence`. NOT VERIFIED: the field that carries the option list.
def _jev_payload(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "model": "jev-latest",
        "state": item_state(item),
        "questions": {
            "category": {
                "type": "choice",
                "instructions": decision_instructions(),
                "options": cp.CATEGORIES,  # VERIFY: option-list field name in the choice schema
            }
        },
    }


def _jev_parse(body: dict[str, Any]) -> tuple[str | None, dict[str, float] | None, float | None]:
    ans = (body.get("answers") or {}).get("category") or {}
    probs = ans.get("probabilities")
    return ans.get("choice"), probs if isinstance(probs, dict) else None, ans.get("confidence")


def _not_public(name: str) -> Callable[[dict[str, Any]], dict[str, Any]]:
    def build(item: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError(
            f"{name}: request schema not published or not verified yet; fill it in from the docs"
        )

    return build


def _generic_parse(
    body: dict[str, Any],
) -> tuple[str | None, dict[str, float] | None, float | None]:
    """Best-effort parse for unknown decision APIs: looks for choice/label and probabilities."""
    node = body.get("decision") or body.get("answer") or body
    probs = node.get("probabilities") or node.get("scores")
    choice = node.get("choice") or node.get("label")
    if choice is None and isinstance(probs, dict) and probs:
        choice = max(probs, key=probs.get)
    conf = node.get("confidence") or (
        probs.get(choice) if isinstance(probs, dict) and choice else None
    )
    return choice, probs if isinstance(probs, dict) else None, conf


DECISION_ENDPOINTS: dict[str, DecisionEndpoint] = {
    "typesafe:jev-latest": DecisionEndpoint(
        provider="typesafe",
        model="jev-latest",
        url="https://api.typesafe.ai/v1/systemone",
        key_env="TYPESAFE_API_KEY",
        build_payload=_jev_payload,
        parse=_jev_parse,
        source_urls=[
            "https://docs.typesafe.ai/introduction/quickstart",
            "https://docs.typesafe.ai/confidence",
        ],
        notes="Early access (waitlist). Input $0.042/M, output free. Reported non-deterministic: cache results "
        "and measure run-to-run variation before trusting it.",
    ),
    "openrouter:typesafe/jev-1.13": DecisionEndpoint(
        provider="openrouter",
        model="typesafe/jev-1.13",
        url="https://openrouter.ai/api/alpha/decisions",
        key_env="OPENROUTER_API_KEY",
        build_payload=_not_public("OpenRouter decisions (alpha)"),
        parse=_generic_parse,
        source_urls=["https://openrouter.ai/blog/insights/what-is-jev/"],
        notes="Alpha endpoint, not chat completions; question ids are not sent to the model, so all meaning goes in "
        "the criteria. Uses the case's OpenRouter key once renewed.",
    ),
    "openai:decisions-preview": DecisionEndpoint(
        provider="openai",
        model="decisions-preview",
        url="https://api.openai.com/v1/decisions",  # VERIFY: guessed path
        key_env="OPENAI_API_KEY",
        build_payload=_not_public("OpenAI Decisions API (limited preview)"),
        parse=_generic_parse,
        source_urls=[
            "https://pasqualepillitteri.it/en/news/19372/openai-launches-decisions-api-jev"
        ],
        notes="Only secondary sources (DevDay, 2026-09-29, limited preview); no official schema or pricing found on "
        "2026-10-08. The URL is a placeholder.",
    ),
    "local:gliner2.5-decide": DecisionEndpoint(
        provider="local",
        model="gliner2.5-decide",
        url="http://localhost:8000/decide",  # VERIFY: depends on how it is served
        key_env="LOCAL_DECISION_TOKEN",
        build_payload=_not_public("GLiNER2.5-Decide (open weights)"),
        parse=_generic_parse,
        source_urls=["https://www.llmreference.com/model/gliner2.5-decide"],
        notes="340M open-weight encoder that takes the label set at call time (listing says released 2026-09-24). "
        "Fits the 6 GB GPU easily; serve it locally (e.g. a small FastAPI wrapper) and keep it out of budget.py.",
    ),
}


@dataclass
class DecisionClassifier:
    endpoint: DecisionEndpoint

    @property
    def provider(self) -> str:
        return self.endpoint.provider

    @property
    def model(self) -> str:
        return self.endpoint.model

    def classify(self, item: dict[str, Any]) -> Prediction:
        ep = self.endpoint
        payload = ep.build_payload(item)
        res = budget.call_http(
            ep.provider,
            ep.model,
            ep.url,
            payload,
            key_env=ep.key_env,
            prompt_version=DECISION_PROMPT_VERSION,
            cache_input=item_state(item),
            purpose="classify",
        )
        choice, probs, conf = ep.parse(res["body"])
        valid = choice in cp.TAXONOMY
        return Prediction(
            choice if valid else None,
            conf,
            probs,
            res["request_id"],
            res["latency_s"],
            res["prompt_tokens"],
            res["completion_tokens"],
            res["cached"],
            valid,
            None if valid else f"choice not in taxonomy: {choice!r}",
        )


def make_classifier(provider: str, model: str, mode: str = "strict") -> ItemClassifier:
    key = f"{provider}:{model}"
    if key in DECISION_ENDPOINTS:
        return DecisionClassifier(DECISION_ENDPOINTS[key])
    if provider == "ollama":
        return OllamaJSONClassifier(model)
    extra = (
        {"chat_template_kwargs": {"enable_thinking": False}}
        if model.startswith("Qwen/Qwen3")
        else None
    )
    return ChatJSONClassifier(provider, model, mode, extra)


def dry_run() -> None:
    """Build every decision payload for one dev item without any network call."""
    item = json.loads((EXP / "dev_items_draft.jsonl").read_text().splitlines()[0])
    for key, ep in DECISION_ENDPOINTS.items():
        try:
            payload = ep.build_payload(item)
            shown = json.dumps(payload, ensure_ascii=False)[:400]
        except NotImplementedError as exc:
            shown = f"(not built) {exc}"
        priced = (ep.provider, ep.model) in budget.PRICES
        print(
            f"{key}\n  url: {ep.url}\n  verified: {ep.verified} | priced in budget.py: {priced}\n  payload: {shown}\n"
        )


if __name__ == "__main__":
    if "--dry-run" in sys.argv:
        dry_run()
    else:
        print(__doc__)
