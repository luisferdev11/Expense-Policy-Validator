"""Spend guard, cache, call log and raw-response store for every model call (OpenRouter only).

The case provides one OpenRouter key with a firm USD 5 budget, and the brief asks for model calls
through it. Every exploration call goes through this module:

- **Cap.** Exploration may spend at most USD 1.00 of the key. Spend is the larger of the cost
  each response reports (`usage.cost`) and the key's measured usage (GET /api/v1/key) against a
  baseline taken before the first call. A call is refused at the cap or after 3,000 calls.
- **Reproducibility.** Temperature 0. Chat models are pinned to one provider endpoint with no
  fallbacks (`research/openrouter_pins.json`, chosen by `scripts/pin_models.py`); an unpinned
  chat model is refused. Prices come from a dated snapshot of the OpenRouter catalogue
  (`research/openrouter_models.json`).
- **Cache.** Responses are cached on disk keyed by model, prompt version and normalised input;
  a cached result keeps the request id that produced it, so re-running costs nothing.
- **Evidence.** Every billed call appends a row to `results/budget_log.jsonl` and saves its raw
  body under `raw/openrouter/<request_id>.json`. Keys come from `.env` and are never printed.

Two kinds of call:
- `call`: chat completions with a strict JSON schema (generative models).
- `call_decision`: POST /api/alpha/decisions (decision models that return a choice and a
  probability distribution instead of text).
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

EXP = Path(__file__).resolve().parent.parent  # explorations/
REPO = EXP.parent
load_dotenv(REPO / ".env")

LOG = EXP / "results" / "budget_log.jsonl"
ERRORS = EXP / "results" / "budget_errors.jsonl"
STATE = EXP / "results" / "budget_state.json"
MODELS_SNAPSHOT = EXP / "research" / "openrouter_models.json"
PINS = EXP / "research" / "openrouter_pins.json"
RAW = EXP / "raw"
CACHE = EXP / "cache"

BASE_URL = "https://openrouter.ai/api/v1"
DECISIONS_URL = "https://openrouter.ai/api/alpha/decisions"
KEY_ENV = "OPENROUTER_API_KEY"
PROVIDER = "openrouter"
REFUSE_USD = 1.00
MAX_CALLS = 3000
MAX_RETRIES = 8
USER_AGENT = "expense-policy-validator-exploration/0.2"

# Pins every chat call to one endpoint: no fallbacks, only endpoints that honour every parameter,
# no providers that may store data. The endpoint tag per model is in research/openrouter_pins.json.
PIN_DEFAULTS: dict[str, Any] = {
    "allow_fallbacks": False,
    "require_parameters": True,
    "data_collection": "deny",
}
# The gpt-oss pin used since 2026-10-08 (DeepInfra bf16), kept so earlier cached runs stay valid.
LEGACY_PINS = {"openai/gpt-oss-120b": "deepinfra/bf16", "openai/gpt-oss-20b": "deepinfra/bf16"}


def _key() -> str:
    return os.environ[KEY_ENV]


def scrub(text: str) -> str:
    """Remove the key from a string before it is logged or printed."""
    k = os.getenv(KEY_ENV)
    if k:
        text = text.replace(k, "***")
    return re.sub(r"\bsk-or-[A-Za-z0-9_\-]{20,}", "***", text)


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


# ------------------------------------------------------------------ prices and pins


def prices() -> dict[str, tuple[float, float]]:
    """USD per million tokens (input, output) from the catalogue snapshot."""
    if not MODELS_SNAPSHOT.exists():
        return {"openai/gpt-oss-120b": (0.037, 0.17), "openai/gpt-oss-20b": (0.03, 0.14)}
    snap = json.loads(MODELS_SNAPSHOT.read_text())
    return {
        m: (float(v["prompt_usd_per_m"]), float(v["completion_usd_per_m"]))
        for m, v in snap["models"].items()
    }


def endpoint_supports(model: str, parameter: str) -> bool:
    """Whether the pinned endpoint accepts a parameter (unknown counts as yes)."""
    pins = json.loads(PINS.read_text()) if PINS.exists() else {}
    params = pins.get(model, {}).get("endpoint_parameters")
    return True if not params else parameter in params


def pin_for(model: str) -> str | None:
    pins = json.loads(PINS.read_text()) if PINS.exists() else {}
    if model in pins:
        return str(pins[model]["endpoint"])
    return LEGACY_PINS.get(model)


def estimated_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    pin, pout = prices().get(model, (0.0, 0.0))
    raw = (prompt_tokens * pin + completion_tokens * pout) / 1_000_000
    return math.ceil(raw * 1e6) / 1e6  # round up to the micro-dollar


# ------------------------------------------------------------------ spend


def key_info() -> dict[str, Any]:
    """Usage and limit of the key (GET /api/v1/key); account identifiers are dropped."""
    resp = requests.get(
        f"{BASE_URL}/key",
        headers={"Authorization": f"Bearer {_key()}", "User-Agent": USER_AGENT},
        timeout=30,
    )
    resp.raise_for_status()
    d = resp.json()["data"]
    return {k: d.get(k) for k in ("limit", "limit_remaining", "usage", "usage_daily", "expires_at")}


def state() -> dict[str, Any]:
    return json.loads(STATE.read_text()) if STATE.exists() else {}


def baseline() -> float:
    """Record the key's usage once, before the first OpenRouter call of the exploration."""
    st = state()
    if st.get("openrouter_baseline_usd") is None:
        info = key_info()
        st["openrouter_baseline_usd"] = float(info["usage"])
        st["openrouter_baseline_at"] = now()
        st["openrouter_key_limit_usd"] = info["limit"]
        STATE.write_text(json.dumps(st, indent=2))
    return float(st["openrouter_baseline_usd"])


def spend_report(measure: bool = False) -> dict[str, Any]:
    """OpenRouter spend of the exploration. Rows from the earlier multi-provider run (Groq,
    DeepInfra) stay in the log as history but do not count against this key."""
    rows = [r for r in _read_jsonl(LOG) if not r.get("cached") and r["provider"] == PROVIDER]
    reported = sum(float(r.get("cost_usd_reported") or r.get("cost_usd_est") or 0) for r in rows)
    calls: dict[str, int] = {}
    for r in rows:
        calls[r["model"]] = calls.get(r["model"], 0) + 1
    measured = None
    st = state()
    if measure and st.get("openrouter_baseline_usd") is not None:
        try:
            measured = float(key_info()["usage"]) - float(st["openrouter_baseline_usd"])
        except Exception:
            measured = None
    return {
        "calls": len(rows),
        "calls_by_model": calls,
        "reported_usd": round(reported, 6),
        "measured_usd": None if measured is None else round(measured, 6),
        "for_cap_usd": round(max(reported, measured or 0.0), 6),
    }


def _guard() -> None:
    baseline()
    rep = spend_report(measure=True)
    if rep["for_cap_usd"] >= REFUSE_USD:
        raise RuntimeError(f"budget refused: OpenRouter spend ${rep['for_cap_usd']:.4f}")
    if rep["calls"] >= MAX_CALLS:
        raise RuntimeError(f"budget refused: {rep['calls']} OpenRouter calls")


# ------------------------------------------------------------------ cache


def cache_key(model: str, prompt_version: str, cache_input: str) -> str:
    raw = "\x1f".join([PROVIDER, model, prompt_version, normalize(cache_input)])
    return hashlib.sha256(raw.encode()).hexdigest()


def _cache_get(key: str) -> dict[str, Any] | None:
    cpath = CACHE / PROVIDER / f"{key}.json"
    if cpath.exists():
        hit = json.loads(cpath.read_text())
        hit["cached"] = True
        return hit
    return None


def _cache_put(key: str, result: dict[str, Any]) -> None:
    cpath = CACHE / PROVIDER / f"{key}.json"
    cpath.parent.mkdir(parents=True, exist_ok=True)
    cpath.write_text(json.dumps(result, ensure_ascii=False))


def _record(
    request_id: str,
    model: str,
    body_text: str,
    pt: int,
    ct: int,
    latency: float,
    prompt_version: str,
    purpose: str,
    served_by: str | None,
    cost_reported: float | None,
    kind: str,
) -> str:
    (RAW / PROVIDER).mkdir(parents=True, exist_ok=True)
    (RAW / PROVIDER / f"{safe_id(request_id)}.json").write_text(scrub(body_text))
    ts = now()
    _append(
        LOG,
        {
            "request_id": request_id,
            "provider": PROVIDER,
            "model": model,
            "kind": kind,
            "prompt_tokens": pt,
            "completion_tokens": ct,
            "latency_s": round(latency, 3),
            "timestamp": ts,
            "cost_usd_est": estimated_cost(model, pt, ct),
            "cost_usd_reported": cost_reported,
            "served_by": served_by,
            "prompt_version": prompt_version,
            "purpose": purpose,
            "cached": False,
        },
    )
    return ts


def _error(model: str, status: int | None, body: str, attempt: int, purpose: str) -> None:
    _append(
        ERRORS,
        {
            "timestamp": now(),
            "provider": PROVIDER,
            "model": model,
            "status": status,
            "attempt": attempt,
            "purpose": purpose,
            "body": scrub(body)[:800],
        },
    )


def _wait(attempt: int, retry_after: str | None) -> None:
    wait = (
        float(retry_after) if retry_after and re.fullmatch(r"[\d.]+", retry_after) else 2.0**attempt
    )
    time.sleep(min(max(wait, 1.0), 120.0))


# ------------------------------------------------------------------ chat models


def call(
    provider: str,
    model: str,
    messages: list[dict[str, str]],
    *,
    prompt_version: str,
    cache_input: str,
    response_format: dict[str, Any] | None = None,
    max_tokens: int = 1024,
    reasoning_effort: str | None = "low",
    extra_body: dict[str, Any] | None = None,
    purpose: str = "",
) -> dict[str, Any]:
    """One chat completion through OpenRouter, pinned to the model's endpoint (or the cache).
    `provider` must be "openrouter"; it is kept in the signature for the earlier scripts."""
    if provider != PROVIDER:
        raise RuntimeError(f"only OpenRouter is used now, not {provider!r}")
    key = cache_key(model, prompt_version, cache_input)
    hit = _cache_get(key)
    if hit:
        return hit
    endpoint = pin_for(model)
    if endpoint is None:
        raise RuntimeError(f"{model} has no pinned endpoint; run scripts/pin_models.py first")
    _guard()
    body: dict[str, Any] = {
        **(extra_body or {}),
        "provider": {**PIN_DEFAULTS, "order": [endpoint]},
    }
    if reasoning_effort is not None:
        body["reasoning"] = {"effort": reasoning_effort}
    kwargs: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "extra_body": body,
    }
    # Temperature 0 everywhere it is accepted; some reasoning models' endpoints reject it.
    temperature_sent = endpoint_supports(model, "temperature")
    if temperature_sent:
        kwargs["temperature"] = 0
    if response_format is not None:
        kwargs["response_format"] = response_format
    client = OpenAI(
        base_url=BASE_URL,
        api_key=_key(),
        max_retries=0,
        timeout=120,
        default_headers={"User-Agent": USER_AGENT},
    )
    for attempt in range(1, MAX_RETRIES + 1):
        t0 = time.monotonic()
        try:
            raw = client.chat.completions.with_raw_response.create(**kwargs)
            latency = time.monotonic() - t0
            body_text = raw.http_response.text
            completion = raw.parse()
            break
        except APIStatusError as exc:
            _error(model, exc.status_code, str(exc.body), attempt, purpose)
            if exc.status_code in (429, 502, 503) and attempt < MAX_RETRIES:
                _wait(attempt, exc.response.headers.get("retry-after"))
                continue
            raise RuntimeError(
                scrub(f"{model} HTTP {exc.status_code}: {str(exc.body)[:300]}")
            ) from None
    request_id = completion.id or f"noid-{key[:16]}"
    usage = completion.usage
    pt = int(getattr(usage, "prompt_tokens", 0) or 0)
    ct = int(getattr(usage, "completion_tokens", 0) or 0)
    try:
        body_json = json.loads(body_text)
    except json.JSONDecodeError:
        body_json = {}
    served_by = body_json.get("provider")
    cost = (body_json.get("usage") or {}).get("cost")
    ts = _record(
        request_id,
        model,
        body_text,
        pt,
        ct,
        latency,
        prompt_version,
        purpose,
        served_by,
        cost,
        "chat",
    )
    result = {
        "request_id": request_id,
        "provider": PROVIDER,
        "model": model,
        "content": completion.choices[0].message.content if completion.choices else None,
        "finish_reason": completion.choices[0].finish_reason if completion.choices else None,
        "prompt_tokens": pt,
        "completion_tokens": ct,
        "latency_s": round(latency, 3),
        "prompt_version": prompt_version,
        "timestamp": ts,
        "served_by": served_by,
        "cost_usd": cost,
        "temperature_sent": temperature_sent,
    }
    _cache_put(key, result)
    return {**result, "cached": False}


# ------------------------------------------------------------------ decision models


def call_decision(
    model: str,
    payload: dict[str, Any],
    *,
    prompt_version: str,
    cache_input: str,
    purpose: str = "",
) -> dict[str, Any]:
    """One request to POST /api/alpha/decisions (or the cache). Returns the parsed body under
    `body`. Decision models are billed on input tokens; `usage.cost` is recorded."""
    key = cache_key(model, prompt_version, cache_input)
    hit = _cache_get(key)
    if hit:
        return hit
    _guard()
    for attempt in range(1, MAX_RETRIES + 1):
        t0 = time.monotonic()
        resp = requests.post(
            DECISIONS_URL,
            json={"model": model, **payload},
            headers={"Authorization": f"Bearer {_key()}", "User-Agent": USER_AGENT},
            timeout=120,
        )
        latency = time.monotonic() - t0
        if resp.status_code < 400:
            break
        _error(model, resp.status_code, resp.text, attempt, purpose)
        if resp.status_code in (429, 502, 503) and attempt < MAX_RETRIES:
            _wait(attempt, resp.headers.get("retry-after"))
            continue
        raise RuntimeError(scrub(f"{model} HTTP {resp.status_code}: {resp.text[:300]}"))
    body = resp.json()
    request_id = str(body.get("id") or resp.headers.get("x-request-id") or f"noid-{key[:16]}")
    usage = body.get("usage") or {}
    pt = int(usage.get("input_tokens", usage.get("prompt_tokens", 0)) or 0)
    ct = int(usage.get("output_tokens", usage.get("completion_tokens", 0)) or 0)
    ts = _record(
        request_id,
        model,
        resp.text,
        pt,
        ct,
        latency,
        prompt_version,
        purpose,
        body.get("provider"),
        usage.get("cost"),
        "decision",
    )
    result = {
        "request_id": request_id,
        "provider": PROVIDER,
        "model": model,
        "served_model": body.get("model"),
        "body": body,
        "prompt_tokens": pt,
        "completion_tokens": ct,
        "latency_s": round(latency, 3),
        "prompt_version": prompt_version,
        "timestamp": ts,
        "served_by": body.get("provider"),
        "cost_usd": usage.get("cost"),
    }
    _cache_put(key, result)
    return {**result, "cached": False}


if __name__ == "__main__":
    print(json.dumps(spend_report(measure=True), indent=2))
