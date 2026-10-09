"""Package 6 runner: classify every dev item with one model and store one prediction row per item.

Usage, from the repository root:

    uv run --no-project --with openai --with python-dotenv --with requests \
        python explorations/lib/run_trial.py ollama qwen3:4b
    uv run ... python explorations/lib/run_trial.py groq openai/gpt-oss-120b

Rows go to explorations/results/trial_runs/<provider>__<model>.jsonl. Every call is cached (ollama under
cache/ollama/, API models through budget.py), so re-running costs nothing. API calls go through
budget.call, which logs, saves raw bodies and enforces the spend cap.
"""

from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Any

import requests

EXP = Path(__file__).resolve().parent.parent  # explorations/
sys.path.insert(0, str(EXP / "lib"))
import budget
import classifier_prompt as cp
from decision_adapters import DECISION_ENDPOINTS, DecisionClassifier

RUNS = EXP / "results" / "trial_runs"
OLLAMA = "http://localhost:11434/api/chat"
# Groq free tier: about 8,000 tokens per minute per model and ~760 prompt tokens per call.
MIN_INTERVAL_S = {"groq": 7.5, "deepinfra": 0.3, "gemini": 4.5}
# Qwen3.5 thinks by default on DeepInfra; switch it off so the call is a plain classification.
EXTRA_BODY = {"Qwen/Qwen3.5-9B": {"chat_template_kwargs": {"enable_thinking": False}}}


def dev_items() -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in (EXP / "dev_set" / "dev_items_draft.jsonl").read_text().splitlines()
        if line.strip()
    ]


def run_file(provider: str, model: str) -> Path:
    return RUNS / f"{provider}__{model.replace('/', '_').replace(':', '_')}.jsonl"


def ollama_classify(model: str, item: dict[str, Any]) -> dict[str, Any]:
    key = hashlib.sha256(
        "\x1f".join([model, cp.PROMPT_VERSION, budget.normalize(cp.cache_input(item))]).encode()
    ).hexdigest()
    cpath = EXP / "cache" / "ollama" / f"{key}.json"
    if cpath.exists():
        return {**json.loads(cpath.read_text()), "cached": True}
    payload = {
        "model": model,
        "messages": cp.messages(item),
        "format": cp.SCHEMA,
        "stream": False,
        "options": {"temperature": 0, "seed": 0, "num_predict": 200},
    }
    if model.startswith("qwen3"):
        payload["think"] = False
    t0 = time.monotonic()
    resp = requests.post(OLLAMA, json=payload, timeout=600)
    latency = time.monotonic() - t0
    resp.raise_for_status()
    body = resp.json()
    res = {
        "content": body.get("message", {}).get("content"),
        "latency_s": round(latency, 3),
        "prompt_tokens": body.get("prompt_eval_count"),
        "completion_tokens": body.get("eval_count"),
        "prompt_version": cp.PROMPT_VERSION,
        "timestamp": budget.now(),
    }
    cpath.parent.mkdir(parents=True, exist_ok=True)
    cpath.write_text(json.dumps(res, ensure_ascii=False))
    return {**res, "cached": False}


def main(provider: str, model: str, mode: str = "strict") -> None:
    RUNS.mkdir(exist_ok=True)
    out = run_file(provider, model)
    done = (
        {json.loads(line)["item_id"] for line in out.read_text().splitlines()}
        if out.exists()
        else set()
    )
    last = 0.0
    for item in dev_items():
        if item["item_id"] in done:
            continue
        row: dict[str, Any] = {
            "item_id": item["item_id"],
            "provider": provider,
            "model": model,
            "prompt_version": cp.PROMPT_VERSION,
        }
        res: dict[str, Any] | None = None
        try:
            if f"{provider}:{model}" in DECISION_ENDPOINTS:
                pred = DecisionClassifier(DECISION_ENDPOINTS[f"{provider}:{model}"]).classify(item)
                row.update(
                    {
                        "predicted_category": pred.category,
                        "confidence": pred.confidence,
                        "probabilities": pred.probabilities,
                        "request_id": pred.request_id,
                        "schema_valid": pred.schema_valid,
                        "latency_s": pred.latency_s,
                        "prompt_tokens": pred.prompt_tokens,
                        "completion_tokens": pred.completion_tokens,
                        "cached": pred.cached,
                        "prompt_version": "dec-v1",
                    }
                )
                if pred.error:
                    row["error"] = pred.error
            elif provider == "ollama":
                res = ollama_classify(model, item)
            else:
                wait = MIN_INTERVAL_S.get(provider, 0) - (time.monotonic() - last)
                fmt = cp.RESPONSE_FORMAT_STRICT if mode == "strict" else {"type": "json_object"}
                is_gpt_oss = "gpt-oss" in model
                res = budget.call(
                    provider,
                    model,
                    cp.messages(item),
                    prompt_version=cp.PROMPT_VERSION,
                    cache_input=cp.cache_input(item),
                    response_format=fmt,
                    max_tokens=1024,
                    reasoning_effort="low" if is_gpt_oss else None,
                    extra_body=EXTRA_BODY.get(model),
                    purpose="06_trial",
                )
                if not res["cached"]:
                    if wait > 0:
                        time.sleep(wait)
                    last = time.monotonic()
                row["request_id"] = res["request_id"]
                row["finish_reason"] = res.get("finish_reason")
            if res is not None:  # chat or ollama; a decision endpoint already filled the row
                cat, conf, err = cp.parse(res["content"])
                row.update(
                    {
                        "predicted_category": cat,
                        "confidence": conf,
                        "schema_valid": cp.schema_valid(res["content"]),
                        "latency_s": res["latency_s"],
                        "prompt_tokens": res.get("prompt_tokens"),
                        "completion_tokens": res.get("completion_tokens"),
                        "cached": res["cached"],
                    }
                )
                if err:
                    row["error"] = err
                    row["raw_content"] = (res["content"] or "")[:300]
        except NotImplementedError as exc:
            print("NOT READY:", exc)
            break
        except Exception as exc:
            if "is not set" in str(exc) or "no price recorded" in str(exc):
                print("NOT READY:", budget.scrub(str(exc)))
                break
            row.update(
                {
                    "predicted_category": None,
                    "confidence": None,
                    "error": budget.scrub(str(exc))[:300],
                }
            )
            if "budget refused" in str(exc):
                print("STOP:", row["error"])
                break
        with out.open("a") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        print(item["item_id"], row.get("predicted_category"), row.get("error", ""), flush=True)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], *(sys.argv[3:4] or ["strict"]))
