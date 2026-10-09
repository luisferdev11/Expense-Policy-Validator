"""Live check through OpenRouter, the deliverable's gateway, verified with /api/v1/generation.

Usage: uv run --no-project --with openai --with python-dotenv --with requests \
           python explorations/scripts/openrouter_check.py

Each gpt-oss model classifies three dev items with the strict schema, pinned to the DeepInfra
bf16 endpoint (budget.OPENROUTER_PIN). Each request id is then looked up with
GET /api/v1/generation, which returns the provider that served it and its billed cost. Rows are
appended to 05_live_check.jsonl (same columns as the Groq and DeepInfra rows, plus the
verification fields) and the generation records to openrouter_generations.jsonl.
"""

import json
import os
import sys
import time
from pathlib import Path

import requests

EXP = Path(__file__).resolve().parent.parent  # explorations/
sys.path.insert(0, str(EXP / "lib"))
import budget
import classifier_prompt as cp

ITEM_IDS = ["DEV-002", "DEV-010", "DEV-026"]  # cooking wine, beer-battered fish, detergent
MODELS = ["openai/gpt-oss-120b", "openai/gpt-oss-20b"]


def generation(request_id: str) -> dict:
    """GET /api/v1/generation?id=...; the record can lag a few seconds behind the call."""
    for attempt in range(6):
        resp = requests.get(
            "https://openrouter.ai/api/v1/generation",
            params={"id": request_id},
            headers={
                "Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}",
                "User-Agent": budget.USER_AGENT,
            },
            timeout=30,
        )
        if resp.status_code == 200:
            return resp.json()["data"]
        time.sleep(2 + 2 * attempt)
    return {"error": f"HTTP {resp.status_code}: {budget.scrub(resp.text)[:200]}"}


items = {
    i["item_id"]: i
    for i in map(json.loads, (EXP / "dev_set" / "dev_items_draft.jsonl").read_text().splitlines())
}
out = EXP / "results" / "05_live_check.jsonl"
done = {
    (r["provider"], r["model"], r["item_id"]) for r in map(json.loads, out.read_text().splitlines())
}
for model in MODELS:
    for iid in ITEM_IDS:
        if ("openrouter", model, iid) in done:
            continue
        item = items[iid]
        res = budget.call(
            "openrouter",
            model,
            cp.messages(item),
            prompt_version=cp.PROMPT_VERSION,
            cache_input=cp.cache_input(item),
            response_format=cp.RESPONSE_FORMAT_STRICT,
            max_tokens=1024,
            purpose="openrouter_live_check",
        )
        gen = generation(res["request_id"])
        keep = (
            "id",
            "model",
            "provider_name",
            "total_cost",
            "tokens_prompt",
            "tokens_completion",
            "native_tokens_prompt",
            "native_tokens_completion",
            "native_tokens_reasoning",
            "latency",
            "generation_time",
            "finish_reason",
        )
        gen_row = {k: gen.get(k) for k in keep} | (
            {"error": gen["error"]} if "error" in gen else {}
        )
        with (EXP / "results" / "openrouter_generations.jsonl").open("a") as fh:
            fh.write(json.dumps(gen_row) + "\n")
        row = {
            "provider": "openrouter",
            "model": model,
            "item_id": iid,
            "request_id": res["request_id"],
            "schema_valid": cp.schema_valid(res["content"]),
            "latency_s": res["latency_s"],
            "prompt_tokens": res["prompt_tokens"],
            "completion_tokens": res["completion_tokens"],
            "finish_reason": res.get("finish_reason"),
            "cached": res["cached"],
            "timestamp": res["timestamp"],
            "served_by": res.get("served_by"),
            "generation_verified": "error" not in gen,
            "generation_provider": gen.get("provider_name"),
            "generation_total_cost_usd": gen.get("total_cost"),
        }
        with out.open("a") as fh:
            fh.write(json.dumps(row) + "\n")
        print(json.dumps(row))
print(json.dumps(budget.spend_report(measure=True)))
