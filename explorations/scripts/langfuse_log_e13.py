"""Log experiment E13 to the local Langfuse so every model call can be inspected and compared.

Usage: uv run --no-project --with langfuse --with openai --with requests --with python-dotenv \
           python explorations/scripts/langfuse_log_e13.py

What ends up in Langfuse (project "Expense-Policy-Validator"):

- **Prompts** (Prompt Management):
  - `classify-item-chat`, label `cls-v1`: the system and user messages sent to generative models.
  - `classify-item-decision`, label `dec-v1`: the instructions and per-category criteria sent to
    decision models.
  A new version is created only if the text or config changed.
- **Dataset** `expense-dev-items-draft`: the 109 synthetic items with their expected category
  (DRAFT labels; the 8 debatable ones were confirmed by Luis, see dev_set/label_reviews.jsonl).
- **Experiment** "E13 item classifier", one run per model. Each item is one trace:
  - root: input = the item, output = the predicted category;
  - one `classify-item` generation: model, the exact messages or decision payload, raw output
    (and the model's reasoning when it returned one), token usage, the cost OpenRouter billed,
    the linked prompt version, and the original OpenRouter request id, provider, latency and
    timestamp in metadata;
  - scores `category_correct`, `restricted_correct`, `confidence`.
  Each run also gets the scores `accuracy`, `macro_f1`, `restricted_f1` and `usd_per_1000_items`.

These are faithful **replays** of the cached calls: no model is called again. Inputs are rebuilt
from the versioned prompt, outputs, usage and cost come from the raw OpenRouter response bodies
in raw/openrouter/. Langfuse's own latency column shows replay time, so the original latency is
in each generation's metadata (`original_latency_s`). Only synthetic data is sent.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

EXP = Path(__file__).resolve().parent.parent
load_dotenv(EXP.parent / ".env")
from langfuse import Evaluation, get_client, propagate_attributes

sys.path.insert(0, str(EXP / "lib"))
import budget
import classifier_prompt as cp
import decision_adapters as da
import run_trial

DATASET = "expense-dev-items-draft"
EXPERIMENT = "E13 item classifier"
CHAT_PROMPT = "classify-item-chat"
DECISION_PROMPT = "classify-item-decision"


def ensure_prompt(lf: Any, name: str, kind: str, prompt: Any, label: str, config: dict) -> Any:
    """Create a prompt version only if the stored one under `label` differs."""
    try:
        current = lf.get_prompt(name, label=label, type=kind, cache_ttl_seconds=0)
        if current.prompt == prompt and (current.config or {}) == config:
            return current
    except Exception:
        pass
    lf.create_prompt(name=name, type=kind, prompt=prompt, labels=[label], config=config)
    return lf.get_prompt(name, label=label, type=kind, cache_ttl_seconds=0)


def raw_body(request_id: str | None) -> dict:
    if not request_id:
        return {}
    path = budget.RAW / "openrouter" / f"{budget.safe_id(request_id)}.json"
    return json.loads(path.read_text()) if path.exists() else {}


def log_row(request_id: str | None) -> dict:
    for line in budget.LOG.read_text().splitlines():
        r = json.loads(line)
        if r.get("request_id") == request_id:
            return r
    return {}


def metrics(rows: list[dict], gold: dict[str, dict]) -> dict[str, float]:
    pred = {r["item_id"]: r.get("predicted_category") for r in rows}
    ids = list(gold)
    acc = sum(pred.get(i) == gold[i]["proposed_category"] for i in ids) / len(ids)
    f1s = []
    for c in cp.TAXONOMY:
        tp = sum(pred.get(i) == c and gold[i]["proposed_category"] == c for i in ids)
        fp = sum(pred.get(i) == c and gold[i]["proposed_category"] != c for i in ids)
        fn = sum(pred.get(i) != c and gold[i]["proposed_category"] == c for i in ids)
        f1s.append(2 * tp / (2 * tp + fp + fn) if (2 * tp + fp + fn) else 0.0)
    pr = {i: cp.TAXONOMY.get(pred.get(i) or "", (False, ""))[0] for i in ids}
    tp = sum(pr[i] and gold[i]["restricted"] for i in ids)
    fp = sum(pr[i] and not gold[i]["restricted"] for i in ids)
    fn = sum(not pr[i] and gold[i]["restricted"] for i in ids)
    return {
        "accuracy": acc,
        "macro_f1": sum(f1s) / len(f1s),
        "restricted_f1": 2 * tp / (2 * tp + fp + fn) if (2 * tp + fp + fn) else 0.0,
    }


def main() -> None:
    lf = get_client()
    if not lf.auth_check():
        sys.exit("Langfuse auth failed: check LANGFUSE_HOST and keys in .env")

    chat_prompt = ensure_prompt(
        lf,
        CHAT_PROMPT,
        "chat",
        [
            {"role": "system", "content": cp.SYSTEM},
            {
                "role": "user",
                "content": "Item: {{description}}\nMerchant: {{merchant}}\nMCC: {{mcc}}",
            },
        ],
        "cls-v1",
        {"response_format": cp.RESPONSE_FORMAT_STRICT, "temperature": 0, "max_tokens": 1024},
    )
    decision_prompt = ensure_prompt(
        lf,
        DECISION_PROMPT,
        "text",
        da.DECISION_INSTRUCTIONS,
        "dec-v1",
        {
            "endpoint": "POST https://openrouter.ai/api/alpha/decisions",
            "question_type": "choice",
            "criteria": {c: ex for c, (_, ex) in cp.TAXONOMY.items()},
        },
    )

    items = run_trial.dev_items()
    gold = {i["item_id"]: i for i in items}
    reviewed = {
        json.loads(x)["item_id"]
        for x in (EXP / "dev_set" / "label_reviews.jsonl").read_text().splitlines()
    }
    lf.create_dataset(
        name=DATASET,
        description="109 synthetic expense line items (labels DRAFT; reviewed items marked)",
        metadata={
            "source": "explorations/dev_set/dev_items_draft.jsonl",
            "sha256": "2565118c...3ecb",
        },
    )
    for it in items:
        lf.create_dataset_item(
            dataset_name=DATASET,
            id=f"dev-{it['item_id']}",
            input={
                "item_id": it["item_id"],
                "description": it["description"],
                "merchant": it["merchant_name"],
                "mcc": it["mcc"],
                "language": it["language"],
            },
            expected_output={"category": it["proposed_category"], "restricted": it["restricted"]},
            metadata={
                "trap": it.get("trap") or "",
                "label_status": "reviewed by Luis" if it["item_id"] in reviewed else "DRAFT",
            },
        )
    dataset = lf.get_dataset(DATASET)

    models = json.loads((EXP / "research" / "openrouter_models.json").read_text())["models"]
    pins = json.loads((EXP / "research" / "openrouter_pins.json").read_text())
    only = set(sys.argv[1:])  # optional: log only these model ids
    for model, meta in models.items():
        if only and model not in only:
            continue
        kind = meta["kind"]
        rows = [json.loads(x) for x in run_trial.run_file(model).read_text().splitlines()]
        by_id = {r["item_id"]: r for r in rows}
        m = metrics(rows, gold)
        costs = [
            float(raw_body(r.get("request_id")).get("usage", {}).get("cost") or 0) for r in rows
        ]
        m["usd_per_1000_items"] = 1000 * sum(costs) / len(costs)
        prompt_tag = rows[0].get("prompt_version") or ("dec-v1" if kind == "decision" else "cls-v1")
        endpoint = pins.get(model, {}).get("endpoint", "decisions API")

        def task(
            *, item, _by_id=by_id, _model=model, _kind=kind, _tag=prompt_tag, _ep=endpoint, **kwargs
        ):
            src = gold[item.input["item_id"]]
            r = _by_id[src["item_id"]]
            body = raw_body(r.get("request_id"))
            lr = log_row(r.get("request_id"))
            usage = body.get("usage") or {}
            if _kind == "chat":
                gen_input = cp.messages(src)
                msg = ((body.get("choices") or [{}])[0]).get("message") or {}
                gen_output = {"role": "assistant", "content": msg.get("content")}
                if msg.get("reasoning"):
                    gen_output["reasoning"] = msg["reasoning"]
                usage_details = {
                    "input": int(usage.get("prompt_tokens") or 0),
                    "output": int(usage.get("completion_tokens") or 0),
                }
                params = {"max_tokens": 1024, "endpoint": _ep}
                if "reasoning-off" in _tag:
                    params["reasoning"] = "disabled"
                elif "reasoning" in (models[_model].get("supported_parameters") or []):
                    params["reasoning_effort"] = "low"
                if budget.endpoint_supports(_model, "temperature"):
                    params["temperature"] = 0
                prompt_obj = chat_prompt
            else:
                gen_input = da.decision_payload(src)
                ans = (body.get("answers") or {}).get("category") or {}
                probs = ans.get("probabilities") or {}
                gen_output = {
                    "choice": ans.get("choice"),
                    "confidence": ans.get("confidence"),
                    "top5_probabilities": dict(sorted(probs.items(), key=lambda kv: -kv[1])[:5]),
                }
                usage_details = {
                    "input": int(usage.get("input_tokens") or 0),
                    "output": int(usage.get("output_tokens") or 0),
                }
                params = {"endpoint": "alpha/decisions"}
                prompt_obj = decision_prompt
            with propagate_attributes(tags=["E13", f"kind-{_kind}"]):
                with lf.start_as_current_observation(
                    as_type="generation",
                    name="classify-item",
                    model=_model,
                    input=gen_input,
                    model_parameters=params,
                    prompt=prompt_obj,
                    metadata={
                        "openrouter_request_id": str(r.get("request_id")),
                        "served_by": str(body.get("provider")),
                        "original_latency_s": str(r.get("latency_s")),
                        "original_timestamp": str(lr.get("timestamp")),
                        "prompt_version": _tag,
                        "replay": "true",
                    },
                ) as gen:
                    gen.update(
                        output=gen_output,
                        usage_details=usage_details,
                        cost_details={"total": float(usage.get("cost") or 0)},
                    )
            return {"category": r.get("predicted_category"), "confidence": r.get("confidence")}

        def category_correct(*, output, expected_output, **kwargs):
            return Evaluation(
                name="category_correct",
                value=float(output["category"] == expected_output["category"]),
                comment=f"predicted {output['category']}, expected {expected_output['category']}",
            )

        def restricted_correct(*, output, expected_output, **kwargs):
            pred_r = cp.TAXONOMY.get(output["category"] or "", (False, ""))[0]
            return Evaluation(
                name="restricted_correct", value=float(pred_r == expected_output["restricted"])
            )

        def confidence(*, output, **kwargs):
            c = output.get("confidence")
            return Evaluation(name="confidence", value=float(c) if c is not None else None)

        def run_scores(*, item_results, _m=m, **kwargs):
            return [
                Evaluation(name=k, value=round(v, 6), comment=f"N={len(gold)} items")
                for k, v in _m.items()
            ]

        dataset.run_experiment(
            name=EXPERIMENT,
            run_name=model,
            description=f"{kind} model through OpenRouter; prompt {prompt_tag}; endpoint {endpoint}; replay of cached calls",
            task=task,
            evaluators=[category_correct, restricted_correct, confidence],
            run_evaluators=[run_scores],
            max_concurrency=8,
            metadata={
                "model": model,
                "kind": kind,
                "prompt_version": prompt_tag,
                "endpoint": endpoint,
                "experiment_id": "E13",
            },
        )
        print(f"logged {model}: " + ", ".join(f"{k}={v:.4f}" for k, v in m.items()), flush=True)
    lf.flush()


if __name__ == "__main__":
    main()
