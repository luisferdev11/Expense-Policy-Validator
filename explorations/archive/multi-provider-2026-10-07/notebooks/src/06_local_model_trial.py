# %% [markdown]
# # 06 · Model trial: local models, gpt-oss and the shortlist (PRELIMINARY)
#
# Every model classifies every one of the synthetic dev items with the same prompt (`cls-v1`,
# `classifier_prompt.py`) and structured JSON output. **Every comparison here is PRELIMINARY**:
# the dev labels are DRAFT labels written by the assistant and not yet verified by Luis. The
# labels were frozen (SHA-256 recorded) before any model saw the items.
#
# - Local (ollama, RTX 3060 Laptop, 6 GB): `qwen3:4b` and `gemma3:4b`.
# - Groq: `openai/gpt-oss-120b`, `openai/gpt-oss-20b` (strict json_schema, reasoning effort low).
# - OpenRouter (the deliverable's gateway, added 2026-10-08): the same two gpt-oss models, pinned to
#   the DeepInfra bf16 endpoint with no fallbacks (`budget.OPENROUTER_PIN`).
# - DeepInfra: the same two gpt-oss models, plus `Qwen/Qwen3.5-9B`, `google/gemma-3-12b-it`
#   (strict json_schema) and `ibm-granite/granite-4.2-8b` (json_object: json_schema is rejected).
#
# The predictions were produced by `run_trial.py` (cached; API calls through `budget.py`, which
# logs every request and saves its raw body). The cell below re-runs it for every model: with the
# cache complete it makes no new calls, it only fills gaps.
#
# **Why these local models.** A 6 GB GPU holds a 3B–4B model at 4-bit with room for context.
# `qwen3:4b` (2.5 GB at Q4_K_M) and `gemma3:4b` (3.3 GB) are both trained for many languages,
# including Japanese, and both support constrained JSON output through ollama's `format`
# parameter. Thinking is switched off for qwen3 so the output is a plain classification.

# %%
from __future__ import annotations

import json
import math
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd
from IPython.display import display
from scipy import stats

REPO = next(p for p in [Path.cwd(), *Path.cwd().parents] if (p / "data" / "policy-docs").is_dir())
EXP = REPO / "explorations"
sys.path.insert(0, str(EXP / "lib"))
import budget
import run_trial

RUNS = [
    ("ollama", "qwen3:4b", "strict"),
    ("ollama", "gemma3:4b", "strict"),
    ("groq", "openai/gpt-oss-120b", "strict"),
    ("groq", "openai/gpt-oss-20b", "strict"),
    ("deepinfra", "openai/gpt-oss-120b", "strict"),
    ("deepinfra", "openai/gpt-oss-20b", "strict"),
    ("deepinfra", "Qwen/Qwen3.5-9B", "strict"),
    ("deepinfra", "google/gemma-3-12b-it", "strict"),
    ("deepinfra", "ibm-granite/granite-4.2-8b", "json_object"),
    ("openrouter", "openai/gpt-oss-120b", "strict"),
    ("openrouter", "openai/gpt-oss-20b", "strict"),
]
for provider, model, mode in RUNS:
    run_trial.main(provider, model, mode)  # no-op when every item is already predicted
print(subprocess.run(["ollama", "list"], capture_output=True, text=True).stdout)

# %%
DEV = [
    json.loads(line)
    for line in (EXP / "dev_set" / "dev_items_draft.jsonl").read_text().splitlines()
    if line.strip()
]
GOLD = {i["item_id"]: i for i in DEV}
TAX_TEXT = (REPO / "data" / "category-taxonomy.md").read_text()
TAXONOMY = {c: r == "yes" for c, r in re.findall(r"^\| `([a-z_]+)` \| (yes|no) \|", TAX_TEXT, re.M)}

rows = []
for provider, model, _ in RUNS:
    for line in run_trial.run_file(provider, model).read_text().splitlines():
        rows.append(json.loads(line))
P = pd.DataFrame(rows)
P["key"] = P["provider"] + ":" + P["model"]
assert P.groupby("key")["item_id"].nunique().eq(len(DEV)).all(), "every model must cover every item"
assert not P.duplicated(["key", "item_id"]).any()
print(f"{len(DEV)} dev items x {P['key'].nunique()} model runs = {len(P)} predictions")

# %% [markdown]
# ## Split into the two prediction files
#
# `06_predictions.jsonl` holds only the local models (named exactly as in `ollama list`) and the
# Groq gpt-oss runs (named exactly `openai/gpt-oss-120b` and `openai/gpt-oss-20b`), because the
# checker keys its files by model name. Every other run goes to `06_predictions_extra.jsonl`.

# %%
FIELDS = [
    "item_id",
    "provider",
    "model",
    "predicted_category",
    "confidence",
    "request_id",
    "error",
    "schema_valid",
    "latency_s",
    "prompt_tokens",
    "completion_tokens",
    "prompt_version",
]


def dump(df: pd.DataFrame, path: Path) -> None:
    with path.open("w") as fh:
        for rec in df.to_dict("records"):
            out = {k: rec.get(k) for k in FIELDS if k in rec}
            out = {
                k: (None if isinstance(v, float) and math.isnan(v) else v) for k, v in out.items()
            }
            if out.get("provider") == "ollama":
                out.pop("request_id", None)
            if out.get("error") is None:
                out.pop("error", None)
            fh.write(json.dumps(out, ensure_ascii=False) + "\n")


main_mask = (P["provider"] == "ollama") | (P["provider"] == "groq")
dump(P[main_mask], EXP / "results" / "06_predictions.jsonl")
dump(P[~main_mask], EXP / "results" / "06_predictions_extra.jsonl")
print(
    "main:",
    sorted(P[main_mask]["model"].unique()),
    "| extra:",
    sorted(P[~main_mask]["key"].unique()),
)

# %% [markdown]
# ## Metrics
#
# Over every dev item, against the DRAFT labels. An error (no parseable category) counts as wrong.
# The predicted restricted flag comes from the taxonomy flag of the predicted category; restricted
# F1 uses restricted = true as the positive class. Macro F1 is the mean of per-category F1 over the
# 21 categories. Accuracy carries its Wilson 95 % interval and its N.


# %%
def wilson(k: int, n: int, z: float = 1.959963984540054) -> tuple[float, float]:
    p = k / n
    den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return c - h, c + h


def metrics(df: pd.DataFrame) -> dict:
    df = df.set_index("item_id").loc[list(GOLD)]
    gold = [GOLD[i]["proposed_category"] for i in df.index]
    gold_r = [GOLD[i]["restricted"] for i in df.index]
    pred = list(df["predicted_category"])
    pred_r = [TAXONOMY.get(p, False) for p in pred]
    n = len(gold)
    correct = sum(p == g for p, g in zip(pred, gold))
    tp = sum(a and b for a, b in zip(pred_r, gold_r))
    fp = sum(a and not b for a, b in zip(pred_r, gold_r))
    fn = sum(not a and b for a, b in zip(pred_r, gold_r))
    rf1 = 2 * tp / (2 * tp + fp + fn) if (2 * tp + fp + fn) else 0.0
    f1s = []
    for c in TAXONOMY:
        ctp = sum(p == c and g == c for p, g in zip(pred, gold))
        cfp = sum(p == c and g != c for p, g in zip(pred, gold))
        cfn = sum(p != c and g == c for p, g in zip(pred, gold))
        f1s.append(2 * ctp / (2 * ctp + cfp + cfn) if (2 * ctp + cfp + cfn) else 0.0)
    lo, hi = wilson(correct, n)
    lat = df["latency_s"].astype(float)
    return {
        "n": n,
        "correct": correct,
        "accuracy": correct / n,
        "accuracy_wilson95": [lo, hi],
        "restricted_f1": rf1,
        "restricted_tp_fp_fn": [tp, fp, fn],
        "macro_f1": float(np.mean(f1s)),
        "errors": int(df["predicted_category"].isna().sum()),
        "schema_valid_rate": float(df["schema_valid"].fillna(False).astype(bool).mean()),
        "latency_s_median": float(lat.median()),
        "latency_s_p95": float(lat.quantile(0.95)),
    }


M = {k: metrics(g) for k, g in P.groupby("key")}
table = pd.DataFrame(M).T[
    [
        "n",
        "correct",
        "accuracy",
        "accuracy_wilson95",
        "restricted_f1",
        "macro_f1",
        "errors",
        "schema_valid_rate",
        "latency_s_median",
        "latency_s_p95",
    ]
]
table.sort_values("accuracy", ascending=False)

# %% [markdown]
# ## Cost per model
#
# Estimated from logged tokens times the published price for the calls this run actually made
# (live check plus trial; cached reuses cost nothing). DeepInfra is also measured as a whole from
# its usage API (billing can lag a few minutes). Local models cost nothing but electricity.

# %%
log = pd.DataFrame(
    [json.loads(line) for line in (EXP / "results" / "budget_log.jsonl").read_text().splitlines()]
)
log["key"] = log["provider"] + ":" + log["model"]
cost = log.groupby("key").agg(
    calls=("request_id", "count"),
    prompt_tokens=("prompt_tokens", "sum"),
    completion_tokens=("completion_tokens", "sum"),
    est_usd=("cost_usd_est", "sum"),
)
cost["est_usd_per_1000_items"] = cost["est_usd"] / cost["calls"] * 1000
spend = budget.spend_report()
print(json.dumps(spend, indent=1))
cost

# %% [markdown]
# ## Write the results files


# %%
def public(m: dict) -> dict:
    return {k: v for k, v in m.items()}


main_results = {}
for key, m in M.items():
    provider, model = key.split(":", 1)
    if provider in ("ollama", "groq"):
        main_results[model] = {
            **public(m),
            "provider": provider,
            "status": "PRELIMINARY: DRAFT labels",
        }
extra_results = {
    key: {**public(m), "status": "PRELIMINARY: DRAFT labels"}
    for key, m in M.items()
    if key.split(":", 1)[0] not in ("ollama", "groq")
}
for key in list(extra_results) + [f"groq:{m}" for m in main_results if m.startswith("openai/")]:
    if key in cost.index:
        target = extra_results.get(key) or main_results[key.split(":", 1)[1]]
        target["cost_est_usd"] = float(cost.loc[key, "est_usd"])
        target["calls_logged"] = int(cost.loc[key, "calls"])
(EXP / "results" / "06_results.json").write_text(json.dumps(main_results, indent=2))
(EXP / "results" / "06_results_extra.json").write_text(json.dumps(extra_results, indent=2))
print("06_results.json:", list(main_results))
print("06_results_extra.json:", list(extra_results))

# %% [markdown]
# ## Per-category accuracy
#
# Accuracy within each DRAFT category (that is, recall per category), with the category's N. Many
# categories have four to nine items, so a single item moves these cells a lot.

# %%
P["gold"] = P["item_id"].map(lambda i: GOLD[i]["proposed_category"])
P["ok"] = P["predicted_category"] == P["gold"]
percat = P.pivot_table(index="gold", columns="key", values="ok", aggfunc="mean")
percat.insert(0, "n", P[P["key"] == P["key"].iloc[0]].groupby("gold").size())
percat.round(2)

# %% [markdown]
# ## Trap items and language
#
# Trap items are the ones tagged in the dev set as named traps, adversarial variants or category
# boundaries. Language accuracy shows whether non-English items are harder.

# %%
P["trap"] = P["item_id"].map(lambda i: GOLD[i].get("trap") or "")
P["trap_kind"] = P["trap"].str.split(":").str[0].replace("", "plain")
P["language"] = P["item_id"].map(lambda i: GOLD[i]["language"])
by_trap = P.pivot_table(index="trap_kind", columns="key", values="ok", aggfunc="mean")
by_trap.insert(0, "n", P[P["key"] == P["key"].iloc[0]].groupby("trap_kind").size())
by_lang = P.pivot_table(index="language", columns="key", values="ok", aggfunc="mean")
by_lang.insert(0, "n", P[P["key"] == P["key"].iloc[0]].groupby("language").size())
display(by_trap.round(2))
by_lang.round(2)

# %% [markdown]
# ## Cross-provider agreement for the same gpt-oss model
#
# Same model id, same prompt, temperature 0, different provider. If the providers served the same
# weights identically, agreement would be total; disagreements show provider-level differences
# (precision, sampling implementation, reasoning handling). The McNemar test on correctness says
# whether either provider is measurably better on these items.


# %%
def paired(a: str, b: str) -> dict:
    x = P[P["key"] == a].set_index("item_id").loc[list(GOLD)]
    y = P[P["key"] == b].set_index("item_id").loc[list(GOLD)]
    agree = float((x["predicted_category"] == y["predicted_category"]).mean())
    bb = int((x["ok"] & ~y["ok"]).sum())
    cc = int((~x["ok"] & y["ok"]).sum())
    p = stats.binomtest(min(bb, cc), bb + cc, 0.5).pvalue if bb + cc else 1.0
    return {
        "a": a,
        "b": b,
        "agreement": agree,
        "a_right_b_wrong": bb,
        "a_wrong_b_right": cc,
        "mcnemar_exact_p": p,
    }


pairs = [
    ("openrouter:openai/gpt-oss-120b", "deepinfra:openai/gpt-oss-120b"),
    ("openrouter:openai/gpt-oss-20b", "deepinfra:openai/gpt-oss-20b"),
    ("groq:openai/gpt-oss-120b", "deepinfra:openai/gpt-oss-120b"),
    ("groq:openai/gpt-oss-20b", "deepinfra:openai/gpt-oss-20b"),
    ("groq:openai/gpt-oss-120b", "groq:openai/gpt-oss-20b"),
    ("groq:openai/gpt-oss-120b", "ollama:qwen3:4b"),
    ("groq:openai/gpt-oss-120b", "deepinfra:Qwen/Qwen3.5-9B"),
]
agreement = pd.DataFrame([paired(a, b) for a, b in pairs])
for key in ["groq:openai/gpt-oss-120b", "groq:openai/gpt-oss-20b"]:
    other = key.replace("groq:", "deepinfra:")
    pr = paired(key, other)
    tgt = main_results[key.split(":", 1)[1]]
    tgt["cross_provider_agreement_vs_deepinfra"] = pr["agreement"]
(EXP / "results" / "06_results.json").write_text(json.dumps(main_results, indent=2))
agreement.round(3)

# %%
x = P[P["key"] == "groq:openai/gpt-oss-120b"].set_index("item_id")
y = P[P["key"] == "deepinfra:openai/gpt-oss-120b"].set_index("item_id")
diff = [i for i in GOLD if x.loc[i, "predicted_category"] != y.loc[i, "predicted_category"]]
pd.DataFrame(
    [
        {
            "item_id": i,
            "description": GOLD[i]["description"],
            "draft_label": GOLD[i]["proposed_category"],
            "groq": x.loc[i, "predicted_category"],
            "deepinfra": y.loc[i, "predicted_category"],
        }
        for i in diff
    ]
)

# %% [markdown]
# ## Where each model fails
#
# Every item at least one model got wrong, with each model's answer. A blank cell means correct.
# Read with care: some "errors" may be DRAFT labels that Luis will overturn (items whose rationale
# says *debatable*).

# %%
wide = P.pivot_table(index="item_id", columns="key", values="predicted_category", aggfunc="first")
okw = P.pivot_table(index="item_id", columns="key", values="ok", aggfunc="first").astype(bool)
fails = wide.where(~okw, "")
fails = fails[(~okw).any(axis=1)]
fails.insert(0, "draft_label", [GOLD[i]["proposed_category"] for i in fails.index])
fails.insert(0, "description", [GOLD[i]["description"] for i in fails.index])
fails.insert(0, "debatable", ["debatable" in GOLD[i]["rationale"].lower() for i in fails.index])
print(f"{len(fails)} of {len(GOLD)} items missed by at least one model")
print("misses per model:", (~okw).sum().to_dict())
fails

# %%
hard = (~okw).sum(axis=1).sort_values(ascending=False)
pd.DataFrame(
    {
        "models_wrong": hard.head(12),
        "description": [GOLD[i]["description"] for i in hard.head(12).index],
        "draft_label": [GOLD[i]["proposed_category"] for i in hard.head(12).index],
        "most_common_wrong_answer": [
            Counter(p for p in wide.loc[i] if p != GOLD[i]["proposed_category"]).most_common(1)
            for i in hard.head(12).index
        ],
    }
)

# %% [markdown]
# ## Reading these numbers
#
# - **N is the number of dev items** (printed above), and every accuracy carries a Wilson
#   interval. The minimum detectable difference at this N is printed in the next cell (same
#   method as notebook 04); the McNemar p-values above are the paired check.
# - **The labels are DRAFT.** Disagreements on items marked *debatable* say as much about the
#   label as about the model. Nothing here should be quoted as a model's accuracy until Luis has
#   verified the labels.
# - **Selection bias.** These runs compare variants; if one is chosen on these 109 items, its
#   number here is optimistic (notebook 04, section 11). The 28 receipts are for the finalist only.


# %%
def power_two_prop(p1: float, p2: float, n: int, alpha: float = 0.05) -> float:
    pbar = (p1 + p2) / 2
    se0 = math.sqrt(2 * pbar * (1 - pbar) / n)
    se1 = math.sqrt(p1 * (1 - p1) / n + p2 * (1 - p2) / n)
    z = stats.norm.ppf(1 - alpha / 2)
    return float(stats.norm.cdf((abs(p1 - p2) - z * se0) / se1))


top = float(table["accuracy"].max())
base = min(top, 0.95)
mdd = next(
    d / 1000 for d in range(1, 1000) if power_two_prop(base - d / 1000, base, len(GOLD)) >= 0.8
)
print(
    f"N={len(GOLD)}, baseline accuracy {base:.3f}: minimum detectable difference (unpaired, alpha 0.05, power 0.8) = {mdd:.3f}"
)


# %% [markdown]
# ## Repeatability through OpenRouter (experiment E11)
#
# The same prompt re-asked twice more for the first 20 items with gpt-oss-120b through OpenRouter
# (pinned endpoint, temperature 0), each compared with the original trial call
# (`determinism_check.py`). The policy engine consumes only the category, but the confidence feeds
# the EXC-03 threshold. If the raw content is not byte-identical, the per-item cache is what makes
# the pipeline's output reproducible (project rule 2).

# %%
det = pd.DataFrame(
    [
        json.loads(line)
        for line in (EXP / "results" / "determinism_openrouter.jsonl").read_text().splitlines()
    ]
)
summary = det.groupby("model").agg(
    repeats=("repeat", "count"),
    items=("item_id", "nunique"),
    identical_content=("same_content", "sum"),
    same_category=("same_category", "sum"),
)
print("served by:", det["served_by"].value_counts().to_dict())
summary
