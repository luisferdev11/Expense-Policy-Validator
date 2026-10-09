"""E11: is the classifier output repeatable at temperature 0 through OpenRouter?

Usage: uv run --no-project --with openai --with python-dotenv --with requests \
           python explorations/scripts/determinism_check.py [model] [n_items] [repeats]

Re-asks the same prompt for the first n dev items `repeats` extra times. The prompt is identical;
only the cache key gets a repeat tag, so each repeat is a fresh, billed call. Each repeat is
compared with the original trial call (trial_runs/openrouter__*.jsonl): the raw content
byte-for-byte, and the parsed category. Rows go to determinism_openrouter.jsonl.
"""

import json
import sys
from pathlib import Path

EXP = Path(__file__).resolve().parent.parent  # explorations/
sys.path.insert(0, str(EXP / "lib"))
import budget
import classifier_prompt as cp

model = sys.argv[1] if len(sys.argv) > 1 else "openai/gpt-oss-120b"
n_items = int(sys.argv[2]) if len(sys.argv) > 2 else 20
repeats = int(sys.argv[3]) if len(sys.argv) > 3 else 2

items = [
    json.loads(line)
    for line in (EXP / "dev_set" / "dev_items_draft.jsonl").read_text().splitlines()
][:n_items]
out = EXP / "results" / "determinism_openrouter.jsonl"
rows = []
for item in items:
    base = budget.call(
        "openrouter",
        model,
        cp.messages(item),
        prompt_version=cp.PROMPT_VERSION,
        cache_input=cp.cache_input(item),
        response_format=cp.RESPONSE_FORMAT_STRICT,
        max_tokens=1024,
        purpose="06_trial",
    )  # cached: the original trial call
    for k in range(1, repeats + 1):
        rep = budget.call(
            "openrouter",
            model,
            cp.messages(item),
            prompt_version=cp.PROMPT_VERSION,
            cache_input=cp.cache_input(item) + f"\x1frepeat={k}",
            response_format=cp.RESPONSE_FORMAT_STRICT,
            max_tokens=1024,
            purpose="e11_determinism",
        )
        row = {
            "item_id": item["item_id"],
            "model": model,
            "repeat": k,
            "request_id": rep["request_id"],
            "base_request_id": base["request_id"],
            "same_content": rep["content"] == base["content"],
            "same_category": cp.parse(rep["content"])[0] == cp.parse(base["content"])[0],
            "served_by": rep.get("served_by"),
        }
        rows.append(row)
        with out.open("a") as fh:
            fh.write(json.dumps(row) + "\n")
n = len(rows)
print(
    f"{model}: {n} repeats over {len(items)} items; identical content {sum(r['same_content'] for r in rows)}/{n}; "
    f"same category {sum(r['same_category'] for r in rows)}/{n}"
)
