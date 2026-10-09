"""Log experiment E13 to the local self-hosted Langfuse: one dataset, one experiment run per model.

Usage: uv run --no-project --with langfuse --with openai --with requests --with python-dotenv \
           python explorations/scripts/langfuse_e13.py

Langfuse is the lab notebook, not the source of truth: the committed JSONL under results/ is.
The dataset `expense-dev-items-draft` holds the 109 synthetic DRAFT items (input: item text,
merchant, MCC; expected output: category and restricted flag). Each experiment run replays the
cached prediction of one model (results/trial_runs/openrouter__<model>.jsonl), so logging costs
no model call; the original OpenRouter request id is kept in each trace's output. Item scores:
category_correct, restricted_correct, confidence. Run scores: accuracy, macro_f1, restricted_f1.
Only synthetic data is sent; nothing from data/receipts.jsonl.
"""

import json
import sys
from pathlib import Path

from dotenv import load_dotenv

EXP = Path(__file__).resolve().parent.parent
load_dotenv(EXP.parent / ".env")
from langfuse import Evaluation, get_client

sys.path.insert(0, str(EXP / "lib"))
import classifier_prompt as cp
import run_trial

DATASET = "expense-dev-items-draft"
EXPERIMENT = "E13 item classifier: OpenRouter models"


def metrics(rows: list[dict], gold: dict[str, dict]) -> dict[str, float]:
    pred = {r["item_id"]: r.get("predicted_category") for r in rows}
    ids = list(gold)
    acc = sum(pred.get(i) == gold[i]["proposed_category"] for i in ids) / len(ids)
    f1s = []
    for c in cp.TAXONOMY:
        tp = sum(pred.get(i) == c and gold[i]["proposed_category"] == c for i in ids)
        fp = sum(pred.get(i) == c and gold[i]["proposed_category"] != c for i in ids)
        fn = sum(pred.get(i) != c and gold[i]["proposed_category"] == c for i in ids)
        f1s.append(2 * tp / (2 * tp + fp + fn) if (2 * tp + fp + fn) else 0.0)
    pr = {i: cp.TAXONOMY.get(pred.get(i) or "", (False, ""))[0] for i in ids}
    tp = sum(pr[i] and gold[i]["restricted"] for i in ids)
    fp = sum(pr[i] and not gold[i]["restricted"] for i in ids)
    fn = sum(not pr[i] and gold[i]["restricted"] for i in ids)
    rf1 = 2 * tp / (2 * tp + fp + fn) if (2 * tp + fp + fn) else 0.0
    return {"accuracy": acc, "macro_f1": sum(f1s) / len(f1s), "restricted_f1": rf1}


def main() -> None:
    lf = get_client()
    if not lf.auth_check():
        sys.exit("Langfuse auth failed: check LANGFUSE_HOST and keys in .env")
    items = run_trial.dev_items()
    gold = {i["item_id"]: i for i in items}
    lf.create_dataset(
        name=DATASET,
        description="109 synthetic expense line items, DRAFT labels (SHA-256 2565118c...3ecb)",
        metadata={"status": "DRAFT", "source": "explorations/dev_set/dev_items_draft.jsonl"},
    )
    for it in items:
        lf.create_dataset_item(
            dataset_name=DATASET,
            id=f"dev-{it['item_id']}",
            input={
                "item_id": it["item_id"],
                "description": it["description"],
                "merchant": it["merchant_name"],
                "mcc": it["mcc"],
                "language": it["language"],
            },
            expected_output={"category": it["proposed_category"], "restricted": it["restricted"]},
            metadata={"trap": it.get("trap") or "", "status": "DRAFT"},
        )
    dataset = lf.get_dataset(DATASET)
    models = json.loads((EXP / "research" / "openrouter_models.json").read_text())["models"]
    pins = json.loads((EXP / "research" / "openrouter_pins.json").read_text())
    for model, meta in models.items():
        path = run_trial.run_file(model)
        if not path.exists():
            print(f"skip {model}: no trial run")
            continue
        rows = [json.loads(line) for line in path.read_text().splitlines()]
        by_id = {r["item_id"]: r for r in rows}
        m = metrics(rows, gold)

        def task(*, item, _by_id=by_id, **kwargs):
            r = _by_id.get(item.input["item_id"], {})
            probs = r.get("probabilities") or {}
            top3 = dict(sorted(probs.items(), key=lambda kv: -kv[1])[:3]) if probs else None
            return {
                "category": r.get("predicted_category"),
                "confidence": r.get("confidence"),
                "top3_probabilities": top3,
                "openrouter_request_id": r.get("request_id"),
                "error": r.get("error"),
            }

        def category_correct(*, output, expected_output, **kwargs):
            return Evaluation(
                name="category_correct",
                value=float(output["category"] == expected_output["category"]),
            )

        def restricted_correct(*, output, expected_output, **kwargs):
            pred_r = cp.TAXONOMY.get(output["category"] or "", (False, ""))[0]
            return Evaluation(
                name="restricted_correct", value=float(pred_r == expected_output["restricted"])
            )

        def confidence(*, output, **kwargs):
            c = output.get("confidence")
            return Evaluation(name="confidence", value=float(c) if c is not None else None)

        def run_scores(*, item_results, _m=m, **kwargs):
            return [
                Evaluation(name=k, value=round(v, 6), comment="N=109 DRAFT items")
                for k, v in _m.items()
            ]

        dataset.run_experiment(
            name=EXPERIMENT,
            run_name=f"{model} ({'dec-v1' if meta['kind'] == 'decision' else 'cls-v1'})",
            description=f"{meta['kind']} model, replayed from the cached OpenRouter run",
            task=task,
            evaluators=[category_correct, restricted_correct, confidence],
            run_evaluators=[run_scores],
            max_concurrency=10,
            metadata={
                "model": model,
                "kind": meta["kind"],
                "prompt_version": "dec-v1" if meta["kind"] == "decision" else "cls-v1",
                "endpoint": pins.get(model, {}).get("endpoint", "decisions-api"),
                "experiment_id": "E13",
                "labels": "DRAFT",
            },
        )
        print(f"logged {model}: " + ", ".join(f"{k}={v:.3f}" for k, v in m.items()), flush=True)
    lf.flush()


if __name__ == "__main__":
    main()
