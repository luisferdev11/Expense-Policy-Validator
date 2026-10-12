# ruff: noqa: E501
"""Run jev-1.13 on the frozen dev set and compare it with the E14 variants (demonstrative).

    uv run python -I frontend/scripts/jev_dev_run.py            # calls OpenRouter, traced in Langfuse
    uv run python -I frontend/scripts/jev_dev_run.py --offline  # replays the local cache, no call

jev is a decision model: it answers with a choice and a probability distribution through
POST /api/alpha/decisions (prompt dec-v1, the E13 payload), so it returns a category only, no
subtype and no recipient. This run is not a registered experiment and decides nothing (product
plan, section 7). It reuses the repository's own pieces and writes only under frontend/:

- the frozen dev set and its hash (`eval.experiments.devset`), read-only;
- the committed predictions of the E14 variants (`explorations/results/iter2/E14`), read-only;
- the statistics of `eval.experiments.decide.e14`, so jev's numbers are computed the way the
  committed ones were;
- the pipeline's tracer: one `classify-dev-item` trace per item with a `classify-item` generation.

The key comes from `.env` (loaded by code, never printed or written). Raw answers are cached in
frontend/.cache (git-ignored); the committed outputs are frontend/data/*.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import subprocess
import sys
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import requests

HERE = Path(__file__).resolve().parent
FRONT = HERE.parent
ROOT = FRONT.parent
sys.path.insert(0, str(ROOT / "explorations" / "lib"))

import decision_adapters as da  # noqa: E402  (explorations/lib, frozen research code, read-only)

from eval.experiments.decide import _load, e14  # noqa: E402
from eval.experiments.devset import frozen_hash, load_frozen  # noqa: E402
from eval.experiments.run_dev import RESULTS  # noqa: E402
from eval.stats import brier, ece  # noqa: E402
from expense_validator.adapters.tracing import make_tracer  # noqa: E402
from expense_validator.domain.normaliser import clean  # noqa: E402
from expense_validator.domain.taxonomy import restricted_for  # noqa: E402

MODEL = "typesafe/jev-1.13"
VARIANT = "jev-1.13"
URL = "https://openrouter.ai/api/alpha/decisions"
CAP_USD = 0.25
RUN_LABEL = "E14x-jev-1.13"
CACHE = FRONT / ".cache" / "jev-dev.jsonl"
DATA = FRONT / "data"
BASELINES = ["gpt-oss-120b", "gpt-oss-20b", "gemma-3-12b", "qwen3.5-9b"]


def load_env() -> None:
    from dotenv import load_dotenv

    candidates = [ROOT / ".env"]
    common = subprocess.run(
        ["git", "rev-parse", "--git-common-dir"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()
    if common:
        candidates.append((ROOT / common).resolve().parent / ".env")
    for path in candidates:
        if path.is_file():
            load_dotenv(path)
            return


def cache_load() -> dict[str, dict[str, Any]]:
    if not CACHE.is_file():
        return {}
    rows = [json.loads(line) for line in CACHE.read_text(encoding="utf-8").splitlines() if line]
    return {r["key"]: r for r in rows}


def cache_save(cache: dict[str, dict[str, Any]]) -> None:
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for _, r in sorted(cache.items())),
        encoding="utf-8",
    )


def payload_for(item: dict[str, Any]) -> dict[str, Any]:
    """The E13 decision payload over the pipeline's normalised text."""
    return da.decision_payload(
        {
            "description": clean(item["description"]),
            "merchant_name": item["merchant_name"],
            "mcc": item["mcc"],
        }
    )


def call(payload: dict[str, Any], key: str) -> dict[str, Any]:
    """One request, retried on rate limits and gateway errors. Never logs the key."""
    import os

    headers = {
        "Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}",
        "User-Agent": "epv-frontend-eval/1",
    }
    for attempt in range(1, 7):
        t0 = time.monotonic()
        resp = requests.post(URL, json={"model": MODEL, **payload}, headers=headers, timeout=120)
        latency = time.monotonic() - t0
        if resp.status_code < 400:
            body = resp.json()
            usage = body.get("usage") or {}
            return {
                "key": key,
                "body": body,
                "latency_s": round(latency, 3),
                "request_id": str(body.get("id") or f"noid-{key[:16]}"),
                "prompt_tokens": int(usage.get("input_tokens", usage.get("prompt_tokens", 0)) or 0),
                "completion_tokens": int(
                    usage.get("output_tokens", usage.get("completion_tokens", 0)) or 0
                ),
                "cost_usd": usage.get("cost"),
                "served_by": body.get("provider"),
            }
        if resp.status_code in (429, 502, 503) and attempt < 6:
            time.sleep(min(30, 2**attempt))
            continue
        raise RuntimeError(f"HTTP {resp.status_code} from the decisions endpoint")
    raise RuntimeError("unreachable")


def run(items: list[dict[str, Any]], offline: bool) -> list[dict[str, Any]]:
    tracer = make_tracer(disabled=offline)
    cache = cache_load()
    spend = sum(r.get("cost_usd") or 0.0 for r in cache.values())
    rows: list[dict[str, Any]] = []
    for item in sorted(items, key=lambda i: i["item_id"]):
        payload = payload_for(item)
        key = hashlib.sha256(
            json.dumps([MODEL, da.DECISION_PROMPT_VERSION, payload], sort_keys=True).encode()
        ).hexdigest()
        with tracer.receipt_trace(
            item["item_id"],
            RUN_LABEL,
            input={k: item[k] for k in ("description", "language", "merchant_name", "mcc")},
            name="classify-dev-item",
        ) as root:
            hit = cache.get(key)
            result = hit
            error: str | None = None
            with tracer.generation(
                "classify-item",
                model=MODEL,
                input=payload,
                model_parameters={"endpoint": "/api/alpha/decisions", "kind": "decision"},
                metadata={
                    "prompt_version": da.DECISION_PROMPT_VERSION,
                    "cache_key": key,
                    "cache_hit": hit is not None,
                },
            ) as gen:
                if result is None:
                    if offline:
                        error = "offline_cache_miss"
                    elif spend >= CAP_USD:
                        error = "budget_refused"
                    else:
                        try:
                            result = call(payload, key)
                            cache[key] = result
                            spend += result.get("cost_usd") or 0.0
                            cache_save(cache)
                        except Exception as exc:
                            error = "gateway_error"
                            gen.update(level="ERROR", status_message=type(exc).__name__)
                answer = ((result or {}).get("body", {}).get("answers") or {}).get("category") or {}
                if result is not None:
                    gen.update(
                        output=answer,
                        usage_details={
                            "input": result["prompt_tokens"],
                            "output": result["completion_tokens"],
                        },
                        cost_details={"total": result.get("cost_usd") or 0.0},
                        metadata={
                            "request_id": result["request_id"],
                            "served_by": result.get("served_by"),
                        },
                    )
            choice = answer.get("choice")
            probs = (
                answer.get("probabilities") if isinstance(answer.get("probabilities"), dict) else {}
            )
            valid = choice in da.cp.TAXONOMY
            category = choice if valid else None
            if error is None and not valid:
                error = "schema_violation"
            row = {
                "item_id": item["item_id"],
                "variant": VARIANT,
                "model_id": MODEL,
                "prompt_version": da.DECISION_PROMPT_VERSION,
                "status": "classified" if category else "unclassified",
                "category": category,
                "restricted": restricted_for(category) if category else None,
                "confidence": answer.get("confidence"),
                "top_probability": probs.get(choice) if choice else None,
                "subtype": "none",
                "recipient_kind": "none",
                "recipient_name": None,
                "request_id": (result or {}).get("request_id"),
                "cost_usd": (result or {}).get("cost_usd"),
                "latency_s": (result or {}).get("latency_s"),
                "served_by": (result or {}).get("served_by"),
                "unclassified_reason": None if category else error,
            }
            root.update(
                output={"predicted": row["category"], "expected": item.get("category")},
                metadata={"experiment": "E14x", "variant": VARIANT},
            )
        rows.append(row)
    tracer.flush(timeout_s=15.0)
    return rows


def pct(values: list[float], q: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(q * len(ordered)))]


def calibration(
    rows: list[dict[str, Any]], items: list[dict[str, Any]], field: str
) -> dict[str, Any] | None:
    expected = {i["item_id"]: i["category"] for i in items}
    pairs = [
        (r[field], r["category"] == expected[r["item_id"]])
        for r in rows
        if r.get(field) is not None and r["status"] == "classified"
    ]
    if len(pairs) < 10:
        return None
    conf, ok = [p[0] for p in pairs], [p[1] for p in pairs]
    return {"n": len(pairs), "brier": round(brier(conf, ok), 4), "ece": round(ece(conf, ok), 4)}


def confusions(rows: list[dict[str, Any]], items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    expected = {i["item_id"]: i["category"] for i in items}
    pairs = Counter(
        (expected[r["item_id"]], r["category"] or "unclassified")
        for r in rows
        if r["category"] != expected[r["item_id"]]
    )
    return [
        {"expected": e, "predicted": p, "count": n}
        for (e, p), n in sorted(pairs.items(), key=lambda x: (-x[1], x[0]))
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()
    if not args.offline:
        load_env()
    items = load_frozen()
    digest = frozen_hash()
    rows = run(items, args.offline)
    failed = [r for r in rows if r["status"] != "classified"]
    print(
        f"{VARIANT}: {len(rows)} items, {len(failed)} unclassified, billed USD {sum(r['cost_usd'] or 0 for r in rows):.6f}",
        file=sys.stderr,
    )

    DATA.mkdir(exist_ok=True)
    (DATA / "jev-1.13-dev.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8"
    )

    results = {name: _load(RESULTS / "E14" / f"{name}.jsonl") for name in BASELINES}
    results[VARIANT] = rows
    comparison = e14(results, items)  # raises if any run still has gateway errors
    latencies = [r["latency_s"] for r in rows if r["latency_s"] is not None]
    summary = {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "dev_set_sha256": digest,
        "n": len(items),
        "model_id": MODEL,
        "prompt_version": da.DECISION_PROMPT_VERSION,
        "served_by": sorted({r["served_by"] for r in rows if r["served_by"]}),
        "variants": comparison["variants"],
        "latency_s": {
            "n": len(latencies),
            "mean": round(statistics.fmean(latencies), 3) if latencies else None,
            "p50": round(pct(latencies, 0.5), 3) if latencies else None,
            "p95": round(pct(latencies, 0.95), 3) if latencies else None,
            "note": "Measured for jev-1.13 only; the committed E14 runs did not record latency.",
        },
        "calibration": {
            "jev-1.13 (top probability)": calibration(rows, items, "top_probability"),
            "jev-1.13 (reported confidence)": calibration(rows, items, "confidence"),
            "gpt-oss-120b (self-reported confidence)": calibration(
                results["gpt-oss-120b"], items, "confidence"
            ),
        },
        "confusions": {
            VARIANT: confusions(rows, items),
            "gpt-oss-120b": confusions(results["gpt-oss-120b"], items),
        },
    }
    (DATA / "classifier-comparison.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print("wrote frontend/data/jev-1.13-dev.jsonl and classifier-comparison.json", file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
