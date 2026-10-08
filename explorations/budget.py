"""Budget guard, router, cache and raw-response store for every API model call in this run.

Rules it enforces (the exploration budget rules):

- Hard cap $0.50 across providers; refuses a call once total spend since start is $0.45 or more,
  or once the run has made 900 billable calls.
- DeepInfra spend is measured from its usage API (baseline at start, delta later). Groq and
  Gemini spend is estimated from logged tokens times published prices, rounded up per call.
  The refusal check uses the larger of measured and estimated spend for DeepInfra.
- Every call appends to budget_log.jsonl and saves the raw response body under
  raw/<provider>/<request_id>.json. Responses are cached on disk keyed by provider, model,
  prompt version and normalized input; a cached result keeps the request_id that produced it.
- Keys are loaded with python-dotenv and never printed, logged or written anywhere.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import time
import unicodedata
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv
from openai import APIStatusError, OpenAI

EXP = Path(__file__).resolve().parent
REPO = EXP.parent
load_dotenv(REPO / ".env")

LOG = EXP / "budget_log.jsonl"
ERRORS = EXP / "budget_errors.jsonl"
STATE = EXP / "budget_state.json"
RAW = EXP / "raw"
CACHE = EXP / "cache"

SPEND_REFUSE_USD = 0.45
MAX_CALLS = 900
MAX_RATE_LIMIT_RETRIES_TOTAL = 400
USER_AGENT = "expense-policy-validator-exploration/0.1"

PROVIDERS: dict[str, dict[str, str]] = {
    "groq": {"base_url": "https://api.groq.com/openai/v1", "key": "GROQ_API_KEY"},
    "deepinfra": {"base_url": "https://api.deepinfra.com/v1/openai", "key": "DEEPINFRA_API_KEY"},
    "gemini": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "key": "GEMINI_API_KEY",
    },
}

# USD per million tokens (input, output). Groq figures checked by Luis on 2026-10-07 and
# re-verified in package 5; the rest are filled from package 5 research before any call.
# A model missing here cannot be called.
PRICES: dict[tuple[str, str], tuple[float, float]] = {
    ("groq", "openai/gpt-oss-120b"): (0.15, 0.60),
    ("groq", "openai/gpt-oss-20b"): (0.075, 0.30),
    # DeepInfra model pages and https://deepinfra.com/pricing, fetched 2026-10-07 (research_notes/providers.md).
    ("deepinfra", "openai/gpt-oss-120b"): (0.037, 0.17),
    ("deepinfra", "openai/gpt-oss-20b"): (0.03, 0.14),
    ("deepinfra", "ibm-granite/granite-4.2-8b"): (0.06, 0.25),
    ("deepinfra", "Qwen/Qwen3.5-9B"): (0.10, 0.15),
    ("deepinfra", "google/gemma-3-12b-it"): (0.05, 0.15),
    # jev launch post, https://typesafe.ai/blog/introducing-system-one-models-and-jev (fetched
    # 2026-10-07): "$0.042 / MTok" input, output "FREE". Usage reporting not yet verified.
    ("typesafe", "jev-latest"): (0.042, 0.0),
    # No price is recorded for OpenAI Decisions or OpenRouter decisions yet, so budget.py refuses
    # those calls until one is added from an official page.
}


def _keys() -> list[str]:
    return [v for v in (os.getenv(p["key"]) for p in PROVIDERS.values()) if v] + [
        v for v in [os.getenv("OPENROUTER_API_KEY")] if v
    ]


def scrub(text: str) -> str:
    """Remove any key value from a string before it is logged or printed."""
    for k in _keys():
        text = text.replace(k, "***")
    return re.sub(r"\b(sk|gsk)-[A-Za-z0-9_\-]{20,}", "***", text)


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def safe_id(request_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", request_id)


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", text)).strip().lower()


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _append(path: Path, row: dict[str, Any]) -> None:
    with path.open("a") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


# ------------------------------------------------------------------ DeepInfra measured spend


def deepinfra_usage_usd() -> float:
    """Total DeepInfra spend this month in USD, from GET /payment/usage (rate is in cents)."""
    key = os.environ["DEEPINFRA_API_KEY"]
    resp = requests.get(
        "https://api.deepinfra.com/payment/usage",
        params={"from": "2026.10"},
        headers={"Authorization": f"Bearer {key}", "User-Agent": USER_AGENT},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    cents = 0.0
    for month in data.get("months", []):
        for item in month.get("items", []):
            cents += float(item.get("units", 0)) * float(item.get("rate", 0))
    return cents / 100


def state() -> dict[str, Any]:
    return json.loads(STATE.read_text()) if STATE.exists() else {}


def start(force: bool = False) -> dict[str, Any]:
    """Record the run start and the DeepInfra baseline once."""
    st = state()
    if st and not force:
        return st
    st = {"started_at": now()}
    try:
        st["deepinfra_baseline_usd"] = deepinfra_usage_usd()
        st["deepinfra_usage_api"] = "ok"
    except Exception as exc:
        st["deepinfra_baseline_usd"] = None
        st["deepinfra_usage_api"] = scrub(f"{type(exc).__name__}: {exc}")[:500]
    STATE.write_text(json.dumps(st, indent=2))
    return st


def estimated_cost(provider: str, model: str, prompt_tokens: int, completion_tokens: int) -> float:
    pin, pout = PRICES[(provider, model)]
    raw = (prompt_tokens * pin + completion_tokens * pout) / 1_000_000
    return math.ceil(raw * 1e6) / 1e6  # round up to the micro-dollar


def spend_report(measure_deepinfra: bool = True) -> dict[str, Any]:
    rows = [r for r in _read_jsonl(LOG) if not r.get("cached")]
    est: dict[str, float] = {}
    calls: dict[str, int] = {}
    for r in rows:
        est[r["provider"]] = est.get(r["provider"], 0.0) + float(r.get("cost_usd_est", 0.0))
        k = f"{r['provider']}:{r['model']}"
        calls[k] = calls.get(k, 0) + 1
    out: dict[str, Any] = {
        "estimated_usd": {k: round(v, 6) for k, v in est.items()},
        "calls": calls,
        "total_calls": len(rows),
    }
    di_measured = None
    st = state()
    if measure_deepinfra and st.get("deepinfra_baseline_usd") is not None:
        try:
            di_measured = deepinfra_usage_usd() - float(st["deepinfra_baseline_usd"])
        except Exception as exc:
            out["deepinfra_measure_error"] = scrub(str(exc))[:300]
    out["deepinfra_measured_usd"] = None if di_measured is None else round(di_measured, 6)
    di = max(est.get("deepinfra", 0.0), di_measured or 0.0)
    out["total_for_cap_usd"] = round(sum(v for k, v in est.items() if k != "deepinfra") + di, 6)
    return out


# ------------------------------------------------------------------ calls


def cache_key(provider: str, model: str, prompt_version: str, cache_input: str) -> str:
    raw = "\x1f".join([provider, model, prompt_version, normalize(cache_input)])
    return hashlib.sha256(raw.encode()).hexdigest()


def _client(provider: str) -> OpenAI:
    cfg = PROVIDERS[provider]
    return OpenAI(
        base_url=cfg["base_url"],
        api_key=os.environ[cfg["key"]],
        max_retries=0,
        timeout=120,
        default_headers={"User-Agent": USER_AGENT},
    )


_retries_used = 0


def call(
    provider: str,
    model: str,
    messages: list[dict[str, str]],
    *,
    prompt_version: str,
    cache_input: str,
    response_format: dict[str, Any] | None = None,
    max_tokens: int = 600,
    reasoning_effort: str | None = "low",
    extra_body: dict[str, Any] | None = None,
    purpose: str = "",
) -> dict[str, Any]:
    """Make (or reuse from cache) one chat completion. Returns a dict with request_id, content,
    usage, latency_s and cached. Raises RuntimeError when the budget refuses the call."""
    global _retries_used
    if (provider, model) not in PRICES:
        raise RuntimeError(f"no price recorded for {provider}:{model}; refusing")
    key = cache_key(provider, model, prompt_version, cache_input)
    cpath = CACHE / provider / f"{key}.json"
    if cpath.exists():
        hit = json.loads(cpath.read_text())
        hit["cached"] = True
        return hit

    rep = spend_report(measure_deepinfra=(provider == "deepinfra"))
    if rep["total_for_cap_usd"] >= SPEND_REFUSE_USD:
        raise RuntimeError(
            f"budget refused: spend ${rep['total_for_cap_usd']:.4f} >= ${SPEND_REFUSE_USD}"
        )
    if rep["total_calls"] >= MAX_CALLS:
        raise RuntimeError(f"budget refused: {rep['total_calls']} calls >= {MAX_CALLS}")

    kwargs: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": 0,
        "max_tokens": max_tokens,
    }
    if response_format is not None:
        kwargs["response_format"] = response_format
    if reasoning_effort is not None:
        kwargs["reasoning_effort"] = reasoning_effort
    if extra_body:
        kwargs["extra_body"] = extra_body

    client = _client(provider)
    attempt = 0
    while True:
        attempt += 1
        t0 = time.monotonic()
        try:
            raw = client.chat.completions.with_raw_response.create(**kwargs)
            latency = time.monotonic() - t0
            body_text = raw.http_response.text
            completion = raw.parse()
            break
        except APIStatusError as exc:
            latency = time.monotonic() - t0
            status = exc.status_code
            err = {
                "timestamp": now(),
                "provider": provider,
                "model": model,
                "status": status,
                "attempt": attempt,
                "purpose": purpose,
                "body": scrub(str(exc.body))[:800],
            }
            _append(ERRORS, err)
            if (
                status in (429, 503)
                and _retries_used < MAX_RATE_LIMIT_RETRIES_TOTAL
                and attempt <= 8
            ):
                _retries_used += 1
                retry_after = exc.response.headers.get("retry-after")
                wait = (
                    float(retry_after)
                    if retry_after and re.fullmatch(r"[\d.]+", retry_after)
                    else 2.0**attempt
                )
                time.sleep(min(max(wait, 1.0), 900.0))
                continue
            raise RuntimeError(
                scrub(f"{provider}:{model} HTTP {status}: {str(exc.body)[:300]}")
            ) from None

    request_id = completion.id or f"noid-{key[:16]}"
    usage = completion.usage
    pt = int(getattr(usage, "prompt_tokens", 0) or 0)
    ct = int(getattr(usage, "completion_tokens", 0) or 0)
    (RAW / provider).mkdir(parents=True, exist_ok=True)
    (RAW / provider / f"{safe_id(request_id)}.json").write_text(scrub(body_text))
    content = completion.choices[0].message.content if completion.choices else None
    row = {
        "request_id": request_id,
        "provider": provider,
        "model": model,
        "prompt_tokens": pt,
        "completion_tokens": ct,
        "latency_s": round(latency, 3),
        "timestamp": now(),
        "cost_usd_est": estimated_cost(provider, model, pt, ct),
        "prompt_version": prompt_version,
        "purpose": purpose,
        "cached": False,
        "ratelimit_remaining_requests": raw.http_response.headers.get(
            "x-ratelimit-remaining-requests"
        ),
        "ratelimit_remaining_tokens": raw.http_response.headers.get("x-ratelimit-remaining-tokens"),
    }
    _append(LOG, row)
    result = {
        "request_id": request_id,
        "provider": provider,
        "model": model,
        "content": content,
        "finish_reason": completion.choices[0].finish_reason if completion.choices else None,
        "prompt_tokens": pt,
        "completion_tokens": ct,
        "latency_s": round(latency, 3),
        "prompt_version": prompt_version,
        "timestamp": row["timestamp"],
    }
    cpath.parent.mkdir(parents=True, exist_ok=True)
    cpath.write_text(json.dumps(result, ensure_ascii=False))
    result["cached"] = False
    return result


def call_http(
    provider: str,
    model: str,
    url: str,
    payload: dict[str, Any],
    *,
    key_env: str,
    prompt_version: str,
    cache_input: str,
    purpose: str = "",
    timeout_s: float = 120.0,
) -> dict[str, Any]:
    """Like `call`, for non-chat JSON APIs (decision models such as jev). Same guard, cache, raw
    body store and log. Returns the parsed response body under `body`. Token counts are read from
    `body.usage` when present (prompt/input and completion/output keys); unknown counts are 0, so
    register a price in PRICES only when the provider documents how usage is reported."""
    if (provider, model) not in PRICES:
        raise RuntimeError(f"no price recorded for {provider}:{model}; refusing")
    key = cache_key(provider, model, prompt_version, cache_input)
    cpath = CACHE / provider / f"{key}.json"
    if cpath.exists():
        hit = json.loads(cpath.read_text())
        hit["cached"] = True
        return hit
    rep = spend_report(measure_deepinfra=False)
    if rep["total_for_cap_usd"] >= SPEND_REFUSE_USD or rep["total_calls"] >= MAX_CALLS:
        raise RuntimeError(
            f"budget refused: {rep['total_for_cap_usd']:.4f} USD, {rep['total_calls']} calls"
        )
    api_key = os.environ.get(key_env)
    if not api_key:
        raise RuntimeError(f"{key_env} is not set; add it to .env to enable {provider}")
    t0 = time.monotonic()
    resp = requests.post(
        url,
        json=payload,
        timeout=timeout_s,
        headers={"Authorization": f"Bearer {api_key}", "User-Agent": USER_AGENT},
    )
    latency = time.monotonic() - t0
    if resp.status_code >= 400:
        _append(
            ERRORS,
            {
                "timestamp": now(),
                "provider": provider,
                "model": model,
                "status": resp.status_code,
                "attempt": 1,
                "purpose": purpose,
                "body": scrub(resp.text)[:800],
            },
        )
        raise RuntimeError(scrub(f"{provider}:{model} HTTP {resp.status_code}: {resp.text[:300]}"))
    body = resp.json()
    request_id = str(body.get("id") or resp.headers.get("x-request-id") or f"noid-{key[:16]}")
    usage = body.get("usage") or {}
    pt = int(usage.get("prompt_tokens", usage.get("input_tokens", 0)) or 0)
    ct = int(usage.get("completion_tokens", usage.get("output_tokens", 0)) or 0)
    (RAW / provider).mkdir(parents=True, exist_ok=True)
    (RAW / provider / f"{safe_id(request_id)}.json").write_text(scrub(resp.text))
    _append(
        LOG,
        {
            "request_id": request_id,
            "provider": provider,
            "model": model,
            "prompt_tokens": pt,
            "completion_tokens": ct,
            "latency_s": round(latency, 3),
            "timestamp": now(),
            "cost_usd_est": estimated_cost(provider, model, pt, ct),
            "prompt_version": prompt_version,
            "purpose": purpose,
            "cached": False,
        },
    )
    result = {
        "request_id": request_id,
        "provider": provider,
        "model": model,
        "body": body,
        "prompt_tokens": pt,
        "completion_tokens": ct,
        "latency_s": round(latency, 3),
        "prompt_version": prompt_version,
        "timestamp": now(),
    }
    cpath.parent.mkdir(parents=True, exist_ok=True)
    cpath.write_text(json.dumps(result, ensure_ascii=False))
    result["cached"] = False
    return result


if __name__ == "__main__":
    print(json.dumps(start(), indent=2))
    print(json.dumps(spend_report(), indent=2))
