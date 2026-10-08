"""Call GET https://openrouter.ai/api/v1/key with the key from .env and record the real outcome.

Appends one row per attempt to openrouter_key_checks.jsonl: timestamp, HTTP status and the
response body (scrubbed of any key). The key itself is never printed or written.
"""

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

EXP = Path(__file__).resolve().parent
sys.path.insert(0, str(EXP))
import os

from budget import USER_AGENT, now, scrub

key = os.environ["OPENROUTER_API_KEY"]
req = urllib.request.Request(
    "https://openrouter.ai/api/v1/key",
    headers={"Authorization": f"Bearer {key}", "User-Agent": USER_AGENT},
)
try:
    with urllib.request.urlopen(req, timeout=30) as resp:
        status, body = resp.status, resp.read().decode()
except urllib.error.HTTPError as exc:
    status, body = exc.code, exc.read().decode()
except Exception as exc:
    status, body = None, f"{type(exc).__name__}: {exc}"
row = {
    "timestamp": now(),
    "url": "GET https://openrouter.ai/api/v1/key",
    "status": status,
    "body": scrub(body)[:1000],
}
with (EXP / "openrouter_key_checks.jsonl").open("a") as fh:
    fh.write(json.dumps(row) + "\n")
print(json.dumps(row))
