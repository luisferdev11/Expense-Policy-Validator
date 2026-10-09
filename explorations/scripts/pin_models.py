"""Snapshot the OpenRouter catalogue for the trial models and pin one endpoint per chat model.

Usage: uv run --no-project --with requests python explorations/scripts/pin_models.py

Writes, with the fetch time:
- research/openrouter_models.json: price per million tokens, modality, context length and
  supported parameters of every model in TRIAL_MODELS, from GET /api/v1/models (no key needed).
- research/openrouter_pins.json: for each chat model, the endpoint every call is pinned to (no
  fallbacks). The rule: among endpoints that are up and support both `structured_outputs` and
  `response_format` (excluding `flex` tiers), prefer the highest precision (bf16/fp16, then
  fp8/int8 or unstated, then fp4/int4) so quantisation does not confound the model comparison,
  then the cheapest by input-plus-output price. Earlier pins are kept, so
  cached results stay valid. Decision models are not pinned: the decisions endpoint takes only a
  model id.

Free (`:free`) variants are excluded: they are rate-limited and may log prompts.
"""

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import requests

EXP = Path(__file__).resolve().parent.parent
TRIAL_MODELS = {
    "chat": [
        "openai/gpt-oss-120b",
        "openai/gpt-oss-20b",
        "qwen/qwen3.5-9b",
        "google/gemma-3-12b-it",
        "google/gemma-3-4b-it",
        "mistralai/ministral-8b-2512",
        "mistralai/mistral-nemo",
        "ibm-granite/granite-4.2-8b",
        "anthropic/claude-haiku-5.5",
        "openai/gpt-6-luna",
    ],
    "decision": [
        "typesafe/jev-1.13",
        "openai/gpt-6-luna-decisions",
        "cloudflare/clef-flash",
        "cloudflare/clef",
        "liquid/d1",
    ],
}
LEGACY = {"openai/gpt-oss-120b": "deepinfra/bf16", "openai/gpt-oss-20b": "deepinfra/bf16"}


def main() -> None:
    fetched = datetime.now(UTC).isoformat(timespec="seconds")
    catalogue = {}
    for query in ("", "?output_modalities=decisions"):
        url = "https://openrouter.ai/api/v1/models" + query
        catalogue.update({m["id"]: m for m in requests.get(url, timeout=30).json()["data"]})
    # The pinned jev version is callable but only its router alias is listed; price it from that.
    ALIASES = {"typesafe/jev-1.13": "~typesafe/jev-latest"}
    snapshot: dict = {
        "fetched_at": fetched,
        "source": "https://openrouter.ai/api/v1/models",
        "models": {},
    }
    missing = []
    for kind, ids in TRIAL_MODELS.items():
        for mid in ids:
            m = catalogue.get(mid) or catalogue.get(ALIASES.get(mid, ""))
            if m is None:
                missing.append(mid)
                continue
            snapshot["models"][mid] = {
                "kind": kind,
                "prompt_usd_per_m": round(float(m["pricing"]["prompt"]) * 1e6, 6),
                "completion_usd_per_m": round(float(m["pricing"]["completion"]) * 1e6, 6),
                "modality": m["architecture"].get("modality"),
                "context_length": m.get("context_length"),
                "supported_parameters": m.get("supported_parameters") or [],
                "catalogue_id": m["id"],
            }
    (EXP / "research" / "openrouter_models.json").write_text(json.dumps(snapshot, indent=1))

    pins_path = EXP / "research" / "openrouter_pins.json"
    pins = json.loads(pins_path.read_text()) if pins_path.exists() else {}
    for mid, tag in LEGACY.items():
        pins.setdefault(
            mid,
            {
                "endpoint": tag,
                "pinned_at": "2026-10-08",
                "why": "pinned before this script; kept so cached runs stay valid",
            },
        )
    for mid in TRIAL_MODELS["chat"]:
        if mid in pins or mid not in snapshot["models"]:
            continue
        eps = requests.get(
            f"https://openrouter.ai/api/v1/models/{mid}/endpoints", timeout=30
        ).json()["data"]["endpoints"]
        ok = [
            e
            for e in eps
            if {"structured_outputs", "response_format"} <= set(e.get("supported_parameters") or [])
            and e.get("status", 0) == 0
            and ":free" not in str(e.get("tag"))
            and "flex" not in str(e.get("tag"))
        ]
        if not ok:
            print(f"{mid}: no endpoint with structured outputs; not pinned")
            continue

        def tier(e: dict) -> int:
            q = str(e.get("quantization") or "").lower()
            return 0 if q in ("bf16", "fp16", "fp32") else 2 if q in ("fp4", "int4") else 1

        best = min(
            ok,
            key=lambda e: (
                tier(e),
                float(e["pricing"]["prompt"]) + float(e["pricing"]["completion"]),
            ),
        )
        pins[mid] = {
            "endpoint": best["tag"],
            "provider_name": best.get("provider_name"),
            "quantization": best.get("quantization"),
            "prompt_usd_per_m": round(float(best["pricing"]["prompt"]) * 1e6, 6),
            "completion_usd_per_m": round(float(best["pricing"]["completion"]) * 1e6, 6),
            "pinned_at": fetched,
            "why": f"highest precision, then cheapest, of {len(ok)} up endpoints with structured outputs",
        }
    # Record the pinned endpoint's own supported parameters (some reasoning models' endpoints
    # do not accept `temperature`; budget.py only sends what the endpoint supports).
    for mid, pin in pins.items():
        if "endpoint_parameters" in pin:
            continue
        eps = requests.get(
            f"https://openrouter.ai/api/v1/models/{mid}/endpoints", timeout=30
        ).json()["data"]["endpoints"]
        match = [e for e in eps if e.get("tag") == pin["endpoint"]]
        pin["endpoint_parameters"] = (
            sorted(match[0].get("supported_parameters") or []) if match else []
        )
    pins_path.write_text(json.dumps(pins, indent=1))
    for mid, p in pins.items():
        print(f"{mid:<34} -> {p['endpoint']:<28} {p.get('provider_name', '')}")
    if missing:
        print("not in the catalogue:", missing)
        sys.exit(1)


if __name__ == "__main__":
    main()
