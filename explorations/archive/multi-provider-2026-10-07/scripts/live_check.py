"""Package 5 live check: strict-JSON-schema calls on a few synthetic dev items.

Usage: uv run --no-project --with openai --with python-dotenv --with requests \
           python explorations/scripts/live_check.py groq|deepinfra

Groq: each gpt-oss model on four dev items. DeepInfra: each gpt-oss model on one item.
Rows go to 05_live_check.jsonl (one per call). Calls use the same cache key as package 6, so the
package 6 pass reuses them instead of paying twice.
"""

import json
import sys
from pathlib import Path

EXP = Path(__file__).resolve().parent.parent  # explorations/
sys.path.insert(0, str(EXP / "lib"))
import budget
import classifier_prompt as cp

ITEM_IDS = [
    "DEV-002",
    "DEV-010",
    "DEV-026",
    "DEV-048",
]  # cooking wine, beer-battered fish, laundry detergent, pt silver bracelet
items = {
    i["item_id"]: i
    for i in map(json.loads, (EXP / "dev_set" / "dev_items_draft.jsonl").read_text().splitlines())
}
provider = sys.argv[1]
plan = {
    "groq": [(m, ITEM_IDS) for m in ["openai/gpt-oss-120b", "openai/gpt-oss-20b"]],
    "deepinfra": [(m, ITEM_IDS[:1]) for m in ["openai/gpt-oss-120b", "openai/gpt-oss-20b"]],
}[provider]
out = EXP / "results" / "05_live_check.jsonl"
done = (
    {
        (r["provider"], r["model"], r["item_id"])
        for r in map(json.loads, out.read_text().splitlines())
    }
    if out.exists()
    else set()
)
for model, ids in plan:
    for iid in ids:
        if (provider, model, iid) in done:
            continue
        item = items[iid]
        try:
            res = budget.call(
                provider,
                model,
                cp.messages(item),
                prompt_version=cp.PROMPT_VERSION,
                cache_input=cp.cache_input(item),
                response_format=cp.RESPONSE_FORMAT_STRICT,
                max_tokens=1024,
                purpose="05_live_check",
            )
        except RuntimeError as exc:
            print(f"{provider} {model} {iid}: FAILED {exc}")
            continue
        row = {
            "provider": provider,
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
        }
        with out.open("a") as fh:
            fh.write(json.dumps(row) + "\n")
        print(json.dumps(row))
print(json.dumps(budget.spend_report(measure_deepinfra=(provider == "deepinfra"))))
