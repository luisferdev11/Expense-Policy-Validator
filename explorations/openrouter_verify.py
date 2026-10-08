"""Verify OpenRouter calls with GET /api/v1/generation, which can lag the call by many minutes.

Usage: uv run --no-project --with openai --with python-dotenv --with requests \
           python explorations/openrouter_verify.py

Looks up every OpenRouter request id in 05_live_check.jsonl and checks that the generation
record exists, names the pinned provider, and bills the same cost the response reported in
`usage.cost` (read from the raw body). Writes openrouter_verification.jsonl (overwritten on each
run) and prints a summary. Re-run later for ids that are still 404.
"""

import json
import os
import sys
from pathlib import Path

import requests

EXP = Path(__file__).resolve().parent
sys.path.insert(0, str(EXP))
import budget

rows = [
    json.loads(line)
    for line in (EXP / "05_live_check.jsonl").read_text().splitlines()
    if '"openrouter"' in line
]
out = []
for r in rows:
    rid = r["request_id"]
    raw = EXP / "raw" / "openrouter" / f"{budget.safe_id(rid)}.json"
    reported = (
        (json.loads(raw.read_text()).get("usage") or {}).get("cost") if raw.exists() else None
    )
    resp = requests.get(
        "https://openrouter.ai/api/v1/generation",
        params={"id": rid},
        headers={
            "Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}",
            "User-Agent": budget.USER_AGENT,
        },
        timeout=30,
    )
    data = resp.json().get("data") if resp.status_code == 200 else None
    out.append(
        {
            "request_id": rid,
            "model": r["model"],
            "checked_at": budget.now(),
            "status": resp.status_code,
            "provider_name": data.get("provider_name") if data else None,
            "total_cost_usd": data.get("total_cost") if data else None,
            "reported_cost_usd": reported,
            "cost_matches": bool(data)
            and reported is not None
            and abs(float(data.get("total_cost") or 0) - float(reported)) < 1e-9,
        }
    )
(EXP / "openrouter_verification.jsonl").write_text("".join(json.dumps(o) + "\n" for o in out))
ok = [o for o in out if o["status"] == 200]
print(
    f"verified {len(ok)}/{len(out)}; provider DeepInfra on all verified: "
    f"{all(o['provider_name'] == 'DeepInfra' for o in ok)}; cost matches on all verified: "
    f"{all(o['cost_matches'] for o in ok)}"
)
