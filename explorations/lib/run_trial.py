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
    if kind == "chat":
        return ChatJSONClassifier(model, "low" if supports(model, "reasoning") else None)
    raise ValueError(f"unknown kind {kind!r}")


def main(kind: str, model: str) -> None:
    RUNS.mkdir(parents=True, exist_ok=True)
    out = run_file(model)
    done = (
        {json.loads(line)["item_id"] for line in out.read_text().splitlines()}
        if out.exists()
        else set()
    )
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
                    "prompt_version": "dec-v1" if kind == "decision" else "cls-v1",
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
