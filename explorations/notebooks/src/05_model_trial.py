# %% [markdown]
# # 05 · Model trial through OpenRouter (experiment E13, PRELIMINARY)
#
# **Question.** Which model should the pipeline's item classifier use, and which confidence
# signal should drive the EXC-03 "uncertain item" threshold?
#
# **Candidates**, all through OpenRouter, the gateway the brief provides:
#
# - **10 generative models.** They are asked for a strict JSON answer: a category and a
#   self-reported confidence (prompt `cls-v1`).
# - **5 decision models.** They return a choice plus a probability distribution over the 21
#   categories instead of text (prompt `dec-v1`, POST `/api/alpha/decisions`).
#
# **What is held fixed:**
# - the 109 synthetic dev items, with DRAFT labels;
# - the input: item text, merchant and MCC;
# - temperature 0, except the two endpoints that reject it (see the deviations below);
# - one pinned endpoint per generative model;
# - every answer cached, with its OpenRouter request id.
#
# **The decision rule was written and committed before any of these runs**, as experiment E13 in
# `research/experiments_plan.yaml`. This notebook applies it mechanically.
#
# Every result here is **PRELIMINARY**. The labels are drafts written by the same assistant that
# wrote the prompts, and an earlier trial showed this set barely separates strong models.

# %%
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import yaml
from IPython.display import display
from scipy import stats

REPO = next(p for p in [Path.cwd(), *Path.cwd().parents] if (p / "data" / "policy-docs").is_dir())
EXP = REPO / "explorations"
sys.path.insert(0, str(EXP / "lib"))
import classifier_prompt as cp
import run_trial

plan = yaml.safe_load((EXP / "research" / "experiments_plan.yaml").read_text())
E13 = next(e for e in plan["experiments"] if e["id"] == "E13")
print("registered at:", E13["registered_at"])
print("\nDECISION RULE (as registered):\n" + E13["decision_rule"])
print("\nDEVIATIONS:\n- " + "\n- ".join(E13.get("deviations", [])))

# %% [markdown]
# ## Load every run

# %%
MODELS = json.loads((EXP / "research" / "openrouter_models.json").read_text())["models"]
PINS = json.loads((EXP / "research" / "openrouter_pins.json").read_text())
DEV = run_trial.dev_items()
GOLD = {i["item_id"]: i for i in DEV}
rows = []
for model, meta in MODELS.items():
    for line in run_trial.run_file(model).read_text().splitlines():
        r = json.loads(line)
        r["kind"] = meta["kind"]
        rows.append(r)
P = pd.DataFrame(rows)
P = P[P["item_id"].isin(GOLD)]
cover = P.groupby("model")["item_id"].nunique()
print(
    f"{len(DEV)} items; runs: {len(cover)}; every run covers every item: {bool((cover == len(DEV)).all())}"
)
P["gold"] = P["item_id"].map(lambda i: GOLD[i]["proposed_category"])
P["ok"] = P["predicted_category"] == P["gold"]
P["error_flag"] = P["predicted_category"].isna()
_ = (EXP / "results" / "05_predictions.jsonl").write_text(
    "".join(
        json.dumps(
            {
                k: (None if isinstance(v, float) and math.isnan(v) else v)
                for k, v in r.items()
                if k not in ("ok", "gold", "error_flag")
            },
            ensure_ascii=False,
        )
        + "\n"
        for r in P.to_dict("records")
    )
)

# %% [markdown]
# ## Metrics per model
#
# Accuracy has a Wilson 95 % interval. Macro F1 averages over the 21 categories. Restricted F1
# treats "restricted = true" as the positive class, with the predicted flag taken from the
# taxonomy. An error (no valid category) counts as wrong. Cost per 1,000 items is the mean
# OpenRouter-reported cost of this model's billed calls, times 1,000.


# %%
def wilson(k: int, n: int, z: float = 1.959963984540054) -> tuple[float, float]:
    p = k / n
    den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return c - h, c + h


log = pd.DataFrame(
    [json.loads(x) for x in (EXP / "results" / "budget_log.jsonl").read_text().splitlines()]
)
log = log[(log["provider"] == "openrouter") & (~log["cached"].astype(bool))]
log["cost"] = log["cost_usd_reported"].fillna(log["cost_usd_est"]).astype(float)
cost_per_call = log.groupby("model")["cost"].mean()


def model_metrics(g: pd.DataFrame) -> dict:
    g = g.set_index("item_id").loc[list(GOLD)]
    n, k = len(g), int(g["ok"].sum())
    lo, hi = wilson(k, n)
    pred = list(g["predicted_category"])
    gold = [GOLD[i]["proposed_category"] for i in g.index]
    f1s = []
    for c in cp.TAXONOMY:
        tp = sum(p == c and t == c for p, t in zip(pred, gold))
        fp = sum(p == c and t != c for p, t in zip(pred, gold))
        fn = sum(p != c and t == c for p, t in zip(pred, gold))
        f1s.append(2 * tp / (2 * tp + fp + fn) if (2 * tp + fp + fn) else 0.0)
    pr = [cp.TAXONOMY.get(p or "", (False, ""))[0] for p in pred]
    gr = [GOLD[i]["restricted"] for i in g.index]
    tp = sum(a and b for a, b in zip(pr, gr))
    fp = sum(a and not b for a, b in zip(pr, gr))
    fn = sum(not a and b for a, b in zip(pr, gr))
    lat = g["latency_s"].astype(float)
    model = g["model"].iloc[0]
    return {
        "kind": g["kind"].iloc[0],
        "n": n,
        "correct": k,
        "accuracy": k / n,
        "wilson_lo": lo,
        "wilson_hi": hi,
        "macro_f1": float(np.mean(f1s)),
        "restricted_f1": 2 * tp / (2 * tp + fp + fn) if (2 * tp + fp + fn) else 0.0,
        "error_rate": float(g["error_flag"].mean()),
        "schema_valid_rate": float(g["schema_valid"].fillna(False).astype(bool).mean()),
        "latency_median_s": float(lat.median()),
        "latency_p95_s": float(lat.quantile(0.95)),
        "usd_per_1000_items": float(cost_per_call.get(model, np.nan) * 1000),
        "endpoint": PINS.get(model, {}).get("endpoint", "decisions API"),
    }


M = pd.DataFrame({m: model_metrics(g) for m, g in P.groupby("model")}).T
num = [
    "accuracy",
    "wilson_lo",
    "wilson_hi",
    "macro_f1",
    "restricted_f1",
    "error_rate",
    "schema_valid_rate",
    "latency_median_s",
    "latency_p95_s",
    "usd_per_1000_items",
]
M[num] = M[num].astype(float)
M.sort_values("accuracy", ascending=False).round(3)

# %%
fig, ax = plt.subplots(figsize=(8, 5))
for kind, marker in [("chat", "o"), ("decision", "s")]:
    sub = M[M["kind"] == kind]
    ax.errorbar(
        sub["usd_per_1000_items"],
        sub["accuracy"],
        yerr=[sub["accuracy"] - sub["wilson_lo"], sub["wilson_hi"] - sub["accuracy"]],
        fmt=marker,
        capsize=3,
        label=kind,
    )
    for name, r in sub.iterrows():
        ax.annotate(
            name.split("/")[-1],
            (r["usd_per_1000_items"], r["accuracy"]),
            fontsize=7,
            xytext=(4, 2),
            textcoords="offset points",
        )
ax.set_xscale("log")
ax.set_xlabel("USD per 1,000 items (log scale)")
ax.set_ylabel("accuracy on 109 DRAFT items (Wilson 95 %)")
ax.set_title("Accuracy against cost")
ax.legend()
plt.tight_layout()

# %% [markdown]
# ## Applying the registered decision rule
#
# **Step 1, exclusions.** A model is excluded if its schema-valid rate is below 0.98 or its error
# rate is above 2 %.

# %%
excluded = M[(M["schema_valid_rate"] < 0.98) | (M["error_rate"] > 0.02)]
eligible = M.drop(excluded.index)
print("excluded:", list(excluded.index) or "none")
excluded[["kind", "schema_valid_rate", "error_rate"]].round(3)

# %% [markdown]
# **Step 2, challengers against the reference.** For every eligible model we run McNemar's exact
# test on the same 109 items against `openai/gpt-oss-120b`.
# - `b`: items the challenger got right and the reference got wrong.
# - `c`: the reverse.
# - A challenger **replaces** the reference only if p < 0.05 *in its favour* (b > c) and its
#   restricted F1 is not lower.

# %%
REF = "openai/gpt-oss-120b"
ok_wide = P.pivot_table(index="item_id", columns="model", values="ok", aggfunc="first").astype(bool)


def mcnemar(a: str, b: str) -> tuple[int, int, float]:
    bb = int((ok_wide[a] & ~ok_wide[b]).sum())
    cc = int((~ok_wide[a] & ok_wide[b]).sum())
    p = stats.binomtest(min(bb, cc), bb + cc, 0.5).pvalue if bb + cc else 1.0
    return bb, cc, float(p)


rows_cmp = []
for m in eligible.index:
    if m == REF:
        continue
    b, c, p = mcnemar(m, REF)
    rows_cmp.append(
        {
            "challenger": m,
            "b_challenger_only_right": b,
            "c_reference_only_right": c,
            "p_value": p,
            "significantly_better": p < 0.05 and b > c,
            "significantly_worse": p < 0.05 and c > b,
            "restricted_f1_not_lower": M.loc[m, "restricted_f1"] >= M.loc[REF, "restricted_f1"],
        }
    )
CMP = pd.DataFrame(rows_cmp).set_index("challenger")
winners = CMP[CMP["significantly_better"] & CMP["restricted_f1_not_lower"]]
CMP.round(4)

# %% [markdown]
# **Step 3, the choice.** If a challenger won step 2, it is chosen; with several winners, the
# cheapest. Otherwise the candidates are the reference plus every eligible model that is not
# significantly worse. Among those, choose the cheapest per 1,000 items, then the lowest median
# latency.

# %%
if len(winners):
    pool = M.loc[winners.index]
    reason = "a challenger beat the reference (McNemar p < 0.05, restricted F1 not lower)"
else:
    non_inferior = [REF] + [m for m in CMP.index if not CMP.loc[m, "significantly_worse"]]
    pool = M.loc[non_inferior]
    reason = "no challenger beat the reference; cheapest among the non-inferior models"
chosen = pool.sort_values(["usd_per_1000_items", "latency_median_s"]).index[0]
print("non-inferior pool:", list(pool.index))
print(f"\nCHOSEN (PRELIMINARY): {chosen}\nreason: {reason}")
print(
    M.loc[
        chosen, ["kind", "accuracy", "restricted_f1", "usd_per_1000_items", "latency_median_s"]
    ].to_string()
)

# %% [markdown]
# **Step 4, the confidence source for EXC-03.** The Brier score here is the mean squared gap
# between the top-label confidence (the probability the model gives its own answer) and whether
# the answer was right. Lower is better. ECE groups the items into 10 confidence bins.
#
# The two kinds of confidence differ:
# - For a generative model it is a number the model **writes**.
# - For a decision model it is a **probability distribution** it returns.
#
# Both are compared on the same footing here.


# %%
def calib(g: pd.DataFrame) -> dict:
    g = g.dropna(subset=["confidence"])
    conf = g["confidence"].astype(float).clip(0, 1).to_numpy()
    y = g["ok"].astype(float).to_numpy()
    brier = float(np.mean((conf - y) ** 2))
    bins = np.minimum((conf * 10).astype(int), 9)
    ece = sum(
        (bins == k).mean() * abs(y[bins == k].mean() - conf[bins == k].mean())
        for k in range(10)
        if (bins == k).any()
    )
    return {
        "n_with_confidence": len(g),
        "brier": brier,
        "ece": float(ece),
        "mean_confidence": float(conf.mean()),
        "accuracy_on_those": float(y.mean()),
    }


CAL = pd.DataFrame(
    {m: calib(g) for m, g in P[P["model"].isin(eligible.index)].groupby("model")}
).T.astype(float)
CAL["kind"] = M.loc[CAL.index, "kind"]
best_conf = CAL.sort_values("brier").index[0]
print("lowest Brier (EXC-03 confidence source, PRELIMINARY):", best_conf)
CAL.sort_values("brier").round(4)


# %%
def reliability(model: str) -> pd.DataFrame:
    g = P[P["model"] == model].dropna(subset=["confidence"])
    conf = g["confidence"].astype(float).clip(0, 1)
    b = pd.cut(conf, [0, 0.5, 0.7, 0.8, 0.9, 0.95, 1.0001], right=False)
    return g.groupby(b, observed=True).agg(
        n=("ok", "size"), mean_conf=("confidence", "mean"), accuracy=("ok", "mean")
    )


for m in [best_conf, REF]:
    print(m)
    display(reliability(m).round(3))

# %% [markdown]
# With 109 items most bins hold only a handful of items, so these tables show direction (over- or
# under-confidence), not a calibrated curve.

# %% [markdown]
# ## What the registered rule got wrong
#
# Step 3 treated "not significantly worse" (McNemar p >= 0.05) as if it meant "as good as". With
# only 109 items, and few items on which two strong models disagree, McNemar has little power. A
# clearly weaker model therefore fails to be *significantly* worse, enters the non-inferior pool,
# and wins on price. **Absence of evidence of a difference is not evidence of equivalence.** The
# rule's mechanical output above stands as the registered result. It is reported, not overridden.
#
# The fix is a **non-inferiority margin**. A challenger counts as "as good as" the reference only
# if the lower end of the 95 % paired bootstrap interval for (challenger − reference) accuracy is
# above −δ. The cell below shows, for illustration only, what δ = 2 points would admit on these
# items. The corrected rule is registered as E14 **before** it is run on the hardened dev set.
# Choosing it on these same items would be exactly the selection bias notebook 04 warns about.

# %%
rng = np.random.default_rng(20261009)
ids = list(GOLD)
ref_ok = ok_wide.loc[ids, REF].to_numpy()
B = 5000
idx = rng.integers(0, len(ids), size=(B, len(ids)))
rows_ni = []
for m in eligible.index:
    if m == REF:
        continue
    diff = ok_wide.loc[ids, m].to_numpy().astype(float) - ref_ok.astype(float)
    boot = diff[idx].mean(axis=1)
    lo, hi = np.percentile(boot, [2.5, 97.5])
    rows_ni.append(
        {
            "model": m,
            "acc_diff_vs_ref": diff.mean(),
            "ci_lo": lo,
            "ci_hi": hi,
            "non_inferior_at_2pt": lo > -0.02,
            "usd_per_1000_items": M.loc[m, "usd_per_1000_items"],
        }
    )
NI = pd.DataFrame(rows_ni).set_index("model").sort_values("acc_diff_vs_ref", ascending=False)
print("illustration only (delta = 0.02, 5,000 paired bootstrap resamples):")
NI.round(4)


# %% [markdown]
# ## Where the models differ: traps, languages, hard items

# %%
P["trap_kind"] = P["item_id"].map(lambda i: (GOLD[i].get("trap") or "plain:").split(":")[0])
P["language"] = P["item_id"].map(lambda i: GOLD[i]["language"])
first = P["model"].iloc[0]
for col in ["trap_kind", "language"]:
    t = P.pivot_table(index=col, columns="model", values="ok", aggfunc="mean")
    t.insert(0, "n", P[P["model"] == first].groupby(col).size())
    display(t.round(2))

# %%
wide = P.pivot_table(index="item_id", columns="model", values="predicted_category", aggfunc="first")
wrong = (~ok_wide).sum(axis=1).sort_values(ascending=False)
hard = wrong[wrong > 0]
print(f"{len(hard)} of {len(GOLD)} items are missed by at least one model; by how many models:")
pd.DataFrame(
    {
        "models_wrong": hard,
        "description": [GOLD[i]["description"] for i in hard.index],
        "draft_label": [GOLD[i]["proposed_category"] for i in hard.index],
        "debatable": ["debatable" in GOLD[i]["rationale"].lower() for i in hard.index],
        "most_common_wrong": [
            wide.loc[i][wide.loc[i] != GOLD[i]["proposed_category"]].value_counts().index[0]
            if (wide.loc[i] != GOLD[i]["proposed_category"]).any()
            else ""
            for i in hard.index
        ],
    }
).head(25)

# %% [markdown]
# ## Write the results

# %%
out = {
    "experiment": "E13",
    "status": "PRELIMINARY: DRAFT labels",
    "n_items": len(DEV),
    "reference": REF,
    "excluded": list(excluded.index),
    "mcnemar_vs_reference": CMP.reset_index().to_dict("records"),
    "chosen_classifier": chosen,
    "choice_reason": reason,
    "exc03_confidence_source": best_conf,
    "models": M.reset_index().rename(columns={"index": "model"}).to_dict("records"),
    "calibration": CAL.reset_index().rename(columns={"index": "model"}).to_dict("records"),
}
_ = (EXP / "results" / "05_results.json").write_text(json.dumps(out, indent=1, default=float))
print("wrote results/05_results.json and results/05_predictions.jsonl")

# %% [markdown]
# ## Reading this honestly
#
# - **N is 109 items.** The minimum detectable difference at this N (computed below, same method
#   as notebook 04) means most gaps between strong models above are noise. The McNemar table,
#   not the ranking, is what the decision uses.
# - **The labels are DRAFT** and written by the same assistant as the prompts. A model that
#   disagrees on an item marked *debatable* may be right.
# - **Selection bias.** The chosen model looks better here than it will on new data, because
#   it was picked on these items. The 28 real receipts are run only once, with the finalist.
# - **Determinism.** Decision models are reported to vary between calls, and E11 showed that
#   gpt-oss's raw text varies too. Every answer used here is cached, so the pipeline's output
#   stays reproducible.


# %%
def power_two_prop(p1: float, p2: float, n: int, alpha: float = 0.05) -> float:
    pbar = (p1 + p2) / 2
    se0 = math.sqrt(2 * pbar * (1 - pbar) / n)
    se1 = math.sqrt(p1 * (1 - p1) / n + p2 * (1 - p2) / n)
    return float(stats.norm.cdf((abs(p1 - p2) - stats.norm.ppf(1 - alpha / 2) * se0) / se1))


base = min(float(M["accuracy"].max()), 0.95)
mdd = next(
    d / 1000 for d in range(1, 1000) if power_two_prop(base - d / 1000, base, len(DEV)) >= 0.8
)
print(
    f"N={len(DEV)}, around {base:.2f} accuracy: minimum detectable difference = {mdd:.3f} "
    "(unpaired, alpha 0.05, power 0.8)"
)
