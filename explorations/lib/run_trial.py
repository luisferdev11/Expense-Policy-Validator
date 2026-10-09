"""Classify every dev item with one OpenRouter model and store one prediction row per item.

Usage, from the repository root:

    uv run --no-project --with openai --with python-dotenv --with requests \
        python explorations/lib/run_trial.py chat openai/gpt-oss-120b
    uv run ... python explorations/lib/run_trial.py decision typesafe/jev-1.13

Rows go to explorations/results/trial_runs/openrouter__<model>.jsonl. Every call goes through
budget.py (spend cap, pinned endpoint for chat models, cache, call log, raw bodies), so re-running
costs nothing once the cache holds the answers. Reasoning effort "low" is sent only to models
whose catalogue entry lists the `reasoning` parameter.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

EXP = Path(__file__).resolve().parent.parent  # explorations/
sys.path.insert(0, str(EXP / "lib"))
import budget
from decision_adapters import ChatJSONClassifier, DecisionClassifier, ItemClassifier

RUNS = EXP / "results" / "trial_runs"
# Models whose reasoning, even at effort "low", exhausts the 1,024-token budget and leaves an
# empty answer. They run with reasoning disabled, as in the earlier direct-provider trial
# (E13 deviation 3), under their own cache tag.
REASONING_OFF = {"qwen/qwen3.5-9b"}


def dev_items() -> list[dict[str, Any]]:
    path = EXP / "dev_set" / "dev_items_draft.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def run_file(model: str) -> Path:
    return RUNS / f"openrouter__{model.replace('/', '_').replace(':', '_').replace('~', '')}.jsonl"


def supports(model: str, parameter: str) -> bool:
    if not budget.MODELS_SNAPSHOT.exists():
        return False
    entry = json.loads(budget.MODELS_SNAPSHOT.read_text())["models"].get(model, {})
    return parameter in (entry.get("supported_parameters") or [])


def classifier(kind: str, model: str) -> ItemClassifier:
    if kind == "decision":
        return DecisionClassifier(model)
    if kind == "chat" and model in REASONING_OFF:
        return ChatJSONClassifier(
            model, None, {"reasoning": {"enabled": False}}, "cls-v1+reasoning-off"
        )
    if kind == "chat":
        return ChatJSONClassifier(model, "low" if supports(model, "reasoning") else None)
    raise ValueError(f"unknown kind {kind!r}")


def main(kind: str, model: str) -> None:
    RUNS.mkdir(parents=True, exist_ok=True)
    out = run_file(model)
    rows = [json.loads(line) for line in out.read_text().splitlines()] if out.exists() else []
    # Transient provider errors (rate limits, 5xx) are not the model's answer: drop and retry them.
    transient = [
        r for r in rows if r.get("error") and ("HTTP 429" in r["error"] or "HTTP 5" in r["error"])
    ]
    if transient:
        rows = [r for r in rows if r not in transient]
        out.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
    done = {r["item_id"] for r in rows}
    clf = classifier(kind, model)
    for item in dev_items():
        if item["item_id"] in done:
            continue
        row: dict[str, Any] = {
            "item_id": item["item_id"],
            "provider": "openrouter",
            "model": model,
            "kind": kind,
        }
        try:
            p = clf.classify(item)
            row.update(
                {
                    "predicted_category": p.category,
                    "confidence": p.confidence,
                    "probabilities": p.probabilities,
                    "request_id": p.request_id,
                    "schema_valid": p.schema_valid,
                    "latency_s": p.latency_s,
                    "prompt_tokens": p.prompt_tokens,
                    "completion_tokens": p.completion_tokens,
                    "finish_reason": p.finish_reason,
                    "served_by": p.served_by,
                    "cached": p.cached,
                    "prompt_version": getattr(clf, "prompt_tag", "dec-v1"),
                }
            )
            if p.error:
                row["error"] = p.error
        except Exception as exc:
            msg = budget.scrub(str(exc))
            if "budget refused" in msg or "no pinned endpoint" in msg:
                print("STOP:", msg)
                break
            row.update({"predicted_category": None, "confidence": None, "error": msg[:300]})
        with out.open("a") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        print(item["item_id"], row.get("predicted_category"), row.get("error", ""), flush=True)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
