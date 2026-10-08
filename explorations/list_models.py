"""List the live model ids on Groq and DeepInfra and save them with the fetch time.

Output: explorations/05_models_live.json. Model listing is free and makes no inference call.
"""

import json
import sys
from pathlib import Path

EXP = Path(__file__).resolve().parent
sys.path.insert(0, str(EXP))
from budget import _client, now

out = {}
for provider in ["groq", "deepinfra"]:
    try:
        ids = sorted(m.id for m in _client(provider).models.list().data)
        out[provider] = {"fetched_at": now(), "count": len(ids), "ids": ids}
    except Exception as exc:
        out[provider] = {"fetched_at": now(), "error": f"{type(exc).__name__}: {str(exc)[:300]}"}
(EXP / "05_models_live.json").write_text(json.dumps(out, indent=1))
for provider, v in out.items():
    print(provider, v.get("count"), v.get("error", ""))
wanted = [
    "gpt-oss",
    "qwen",
    "gemma",
    "llama-3.1-8b",
    "llama-3.2",
    "mistral",
    "granite",
    "phi",
    "ministral",
]
for provider, v in out.items():
    for mid in v.get("ids", []):
        if any(w in mid.lower() for w in wanted):
            print(f"  {provider}: {mid}")
