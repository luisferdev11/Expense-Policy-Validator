# %% [markdown]
# # 04 · How we measure: a study guide
#
# This notebook explains every number the evaluation will report, so each one can be defended
# without notes. Every concept follows the same six steps:
#
# 1. **The question.** What decision does this number help with?
# 2. **The intuition.** The idea in one or two sentences, before any formula.
# 3. **By hand.** A tiny example small enough to do on paper. The code prints every arithmetic
#    step, so you can follow and check it.
# 4. **On our data.** The same calculation on the real E13 model runs from notebook 05 (109
#    synthetic DRAFT items, 15 models through OpenRouter).
# 5. **What it means for us.** The decision it changes.
# 6. **Check yourself.** One question. Answer it before you read the answer.
#
# No number in the prose is typed by hand. Every value comes from a cell.

# %%
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

REPO = next(p for p in [Path.cwd(), *Path.cwd().parents] if (p / "data" / "policy-docs").is_dir())
EXP = REPO / "explorations"
sys.path.insert(0, str(EXP / "lib"))
import classifier_prompt as cp

rng = np.random.default_rng(20261009)
RESULTS: dict = {}

DEV = {
    json.loads(x)["item_id"]: json.loads(x)
    for x in (EXP / "dev_set" / "dev_items_draft.jsonl").read_text().splitlines()
}
P = pd.DataFrame(
    [json.loads(x) for x in (EXP / "results" / "05_predictions.jsonl").read_text().splitlines()]
)
P["gold"] = P["item_id"].map(lambda i: DEV[i]["proposed_category"])
P["ok"] = P["predicted_category"] == P["gold"]
OK = P.pivot_table(index="item_id", columns="model", values="ok", aggfunc="first").astype(bool)
N = len(DEV)
REF = "openai/gpt-oss-120b"
print(f"{N} dev items, {OK.shape[1]} models loaded from notebook 05")

# %% [markdown]
# ---
# ## 1. Accuracy and how unsure we are about it: the Wilson interval
#
# **The question.** A model got *k* of *n* items right. How good is it really, given that *n* is
# small?
#
# **The intuition.** 105 of 109 is a measurement, not the truth. Re-run the experiment on 109
# *different* items of the same kind and you would get a slightly different count. An interval
# says which true accuracies are consistent with what we saw. The fewer the items, the wider it
# is. The textbook "p ± 1.96·√(p(1−p)/n)" breaks down near 0 % or 100 % and with small *n*; it
# can even go below 0. The **Wilson** interval does not.
#
# **The formula.** With p = k/n and z = 1.96 (for 95 %):
# centre = (p + z²/2n) / (1 + z²/n), half-width = z·√(p(1−p)/n + z²/4n²) / (1 + z²/n).


# %%
def wilson(k: int, n: int, z: float = 1.959963984540054) -> tuple[float, float]:
    p = k / n
    den = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / den
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return centre - half, centre + half


# By hand: the brief's example, 1 false positive among 9 clean receipts.
k, n, z = 1, 9, 1.96
p = k / n
den = 1 + z * z / n
centre = (p + z * z / (2 * n)) / den
half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
print(f"p = {k}/{n} = {p:.4f}")
print(f"denominator = 1 + {z}^2/{n} = {den:.4f}")
print(f"centre = ({p:.4f} + {z}^2/(2*{n})) / {den:.4f} = {centre:.4f}")
print(
    f"half-width = {z} * sqrt({p:.4f}*{1 - p:.4f}/{n} + {z}^2/(4*{n}^2)) / {den:.4f} = {half:.4f}"
)
print(f"Wilson 95 %: [{centre - half:.4f}, {centre + half:.4f}]")
wald = (p - z * math.sqrt(p * (1 - p) / n), p + z * math.sqrt(p * (1 - p) / n))
print(f"textbook interval for comparison: [{wald[0]:.4f}, {wald[1]:.4f}]  <- goes below zero")
RESULTS["wilson_1_of_9"] = [round(x, 4) for x in wilson(1, 9)]

# %% [markdown]
# **On our data.** Accuracy of each model on the 109 items, with its Wilson interval.

# %%
acc = (
    pd.DataFrame(
        [
            {
                "model": m,
                "correct": int(OK[m].sum()),
                "n": N,
                "accuracy": OK[m].mean(),
                "wilson_lo": wilson(int(OK[m].sum()), N)[0],
                "wilson_hi": wilson(int(OK[m].sum()), N)[1],
            }
            for m in OK.columns
        ]
    )
    .set_index("model")
    .sort_values("accuracy", ascending=False)
)
overlap = acc["wilson_lo"].max() < acc["wilson_hi"].min()
print("Do all intervals share a common point?", overlap)
print(
    f"best lower bound {acc['wilson_lo'].max():.3f}; worst upper bound {acc['wilson_hi'].min():.3f}"
)
acc.round(3)

# %% [markdown]
# **What it means for us.** A ranking by point accuracy invites "model A beats model B". Where
# the intervals overlap heavily, the data cannot back that sentence. Every accuracy we report
# carries its *n* and its interval.
#
# **Check yourself.** If a model scored 109 out of 109, is its true accuracy 100 %? *(The next
# cell answers.)*

# %%
lo, hi = wilson(N, N)
print(
    f"109/109 gives a Wilson interval of [{lo:.3f}, {hi:.3f}]: a perfect score on {N} items is "
    f"consistent with a true accuracy as low as {lo:.1%}."
)

# %% [markdown]
# ---
# ## 2. Precision, recall and F1 for "restricted"
#
# **The question.** The engine needs to know whether an item is *restricted* (alcohol, tobacco,
# personal electronics, and so on). How good is the classifier at that yes/no decision?
#
# **The intuition.** There are two different ways to be wrong:
# - **A false alarm.** Calling coffee "restricted". Reviewers lose trust and time.
# - **A miss.** Calling cooking wine "not restricted". A violation walks through.
#
# Each error has its own metric:
# - **Precision** = TP / (TP + FP): of what we flagged, how much was right?
# - **Recall** = TP / (TP + FN): of what we should have flagged, how much did we catch?
# - **F1** = 2·P·R / (P + R): their harmonic mean. It is only high when both are high.
#
# F1 ignores the true negatives, which is what we want when the positive class is the one we
# care about.


# %%
def prf(tp: int, fp: int, fn: int) -> tuple[float, float, float]:
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    return p, r, (2 * p * r / (p + r) if p + r else 0.0)


# By hand: 10 items, 4 truly restricted. The model flags 5; 3 of them are right.
tp, fp, fn = 3, 2, 1
p_, r_, f_ = prf(tp, fp, fn)
print(f"precision = TP/(TP+FP) = {tp}/({tp}+{fp}) = {p_:.3f}")
print(f"recall    = TP/(TP+FN) = {tp}/({tp}+{fn}) = {r_:.3f}")
print(f"F1        = 2*{p_:.3f}*{r_:.3f}/({p_:.3f}+{r_:.3f}) = {f_:.3f}")

# %% [markdown]
# **On our data.** The restricted flag of a prediction comes from the taxonomy entry of the
# predicted category.


# %%
def restricted_counts(m: str) -> tuple[int, int, int]:
    g = P[P["model"] == m]
    pred = g["predicted_category"].map(lambda c: cp.TAXONOMY.get(c or "", (False, ""))[0])
    gold = g["item_id"].map(lambda i: DEV[i]["restricted"])
    return int((pred & gold).sum()), int((pred & ~gold).sum()), int((~pred & gold).sum())


rows = []
for m in OK.columns:
    tp, fp, fn = restricted_counts(m)
    pr, rc, f1 = prf(tp, fp, fn)
    rows.append(
        {
            "model": m,
            "TP": tp,
            "FP (false alarms)": fp,
            "FN (misses)": fn,
            "precision": pr,
            "recall": rc,
            "restricted_F1": f1,
        }
    )
pd.DataFrame(rows).set_index("model").sort_values("restricted_F1", ascending=False).round(3)

# %% [markdown]
# **What it means for us.** A miss (FN) on a restricted item can let a violation through. A
# false alarm (FP) sends a clean receipt to an auditor. When restricted F1 values are close, read
# the FN column first.
#
# **Check yourself.** A model that flags *every* item as restricted: what is its recall, and
# what happens to its precision?

# %%
n_restricted = sum(DEV[i]["restricted"] for i in DEV)
print(
    f"Flag all {N}: recall = {n_restricted}/{n_restricted} = 1.0, precision = "
    f"{n_restricted}/{N} = {n_restricted / N:.3f}. Perfect recall alone means nothing."
)

# %% [markdown]
# ---
# ## 3. Macro against micro F1 when categories are tiny
#
# **The question.** We have 21 categories, and some have only 4 or 5 items. What does one
# number for "category quality" hide?
#
# **The intuition.**
# - **Micro F1** pools all items. With one label per item it equals accuracy, so big categories
#   dominate it.
# - **Macro F1** averages the F1 of each category, so a 4-item category weighs as much as a
#   15-item one.
#
# With tiny categories, a single item can move one category's F1 by a lot, and macro F1 with it.
# The brief asks for macro F1, so we report it **with** each category's N.

# %%
counts = pd.Series({i: DEV[i]["proposed_category"] for i in DEV}).value_counts()
K = len(cp.TAXONOMY)
small = counts[counts == counts.min()]
print(f"{K} categories; items per category range from {counts.min()} to {counts.max()}")
print(
    f"One wrong item in a {counts.min()}-item category moves that category's recall by "
    f"1/{counts.min()} = {1 / counts.min():.3f}, macro F1 by roughly that over {K} "
    f"(about {1 / counts.min() / K:.3f}), and micro F1 (accuracy) by 1/{N} = {1 / N:.3f}."
)


# %%
def macro_f1(pred: pd.Series, gold: pd.Series) -> float:
    f1s = []
    for c in cp.TAXONOMY:
        tp = int(((pred == c) & (gold == c)).sum())
        fp = int(((pred == c) & (gold != c)).sum())
        fn = int(((pred != c) & (gold == c)).sum())
        f1s.append(2 * tp / (2 * tp + fp + fn) if (2 * tp + fp + fn) else 0.0)
    return float(np.mean(f1s))


g = P[P["model"] == REF].set_index("item_id")
print(
    f"{REF}: micro F1 (accuracy) {g['ok'].mean():.3f}, macro F1 "
    f"{macro_f1(g['predicted_category'], g['gold']):.3f}"
)

# %% [markdown]
# **What it means for us.** Macro F1 is noisy at this N. The per-category table with N is the
# honest companion to it.
#
# **Check yourself.** Why can macro F1 fall *below* accuracy? *(Because a small category done
# badly drags the average down as much as a large category would.)*

# %% [markdown]
# ---
# ## 4. Are two models really different? McNemar's test
#
# **The question.** jev scored more than gpt-oss-120b on the same 109 items. Is that a real
# difference or luck?
#
# **The intuition.** Both models saw the **same** items, so only the items where they *disagree*
# carry information:
# - **b**: items model A got right and model B got wrong.
# - **c**: the reverse.
#
# If the models were equally good, each disagreement would be a fair coin flip. McNemar asks how
# surprising a split of b against c is for a fair coin. Items both got right, or both got wrong,
# say nothing about which is better.


# %%
def mcnemar(a: str, b: str) -> tuple[int, int, float]:
    bb = int((OK[a] & ~OK[b]).sum())
    cc = int((~OK[a] & OK[b]).sum())
    p = stats.binomtest(min(bb, cc), bb + cc, 0.5).pvalue if bb + cc else 1.0
    return bb, cc, float(p)


# By hand: 4 disagreements, all 4 in A's favour.
b, c = 4, 0
n_disc = b + c
tail = sum(math.comb(n_disc, i) for i in range(min(b, c) + 1)) / 2**n_disc
print(
    f"{n_disc} coin flips; chance of a split at least as lopsided as {b}-{c}, on one side: "
    f"{tail:.4f}; on either side (two-sided): {min(1, 2 * tail):.4f}"
)
RESULTS["mcnemar"] = {
    "b": b,
    "c": c,
    "p_value": round(min(1, 2 * tail), 6),
    "test": "exact binomial, two-sided",
}

# %% [markdown]
# **On our data.**

# %%
for m in [
    "typesafe/jev-1.13",
    "anthropic/claude-haiku-5.5",
    "openai/gpt-oss-20b",
    "ibm-granite/granite-4.2-8b",
]:
    bb, cc, pv = mcnemar(m, REF)
    print(f"{m:<30} vs {REF}: b={bb}, c={cc}, exact p={pv:.3f}")

# %% [markdown]
# **What it means for us.** Even a perfect 4-to-0 split is not significant at the 5 % level.
# With so few disagreements, the test cannot tell strong models apart. That is not a flaw in
# the test; it is a fact about this sample.
#
# **Check yourself.** How many disagreements, all one way, are needed before p < 0.05?

# %%
need = next(n_ for n_ in range(1, 30) if 2 * 0.5**n_ < 0.05)
print(f"{need} disagreements, all in one direction (two-sided exact p = {2 * 0.5**need:.4f}).")

# %% [markdown]
# ---
# ## 5. The bootstrap: an interval for anything
#
# **The question.** Wilson works for one proportion. What about the *difference* between two
# models, or macro F1, which have no simple formula?
#
# **The intuition.** Pretend our 109 items are the whole world. Draw 109 items from them *with
# replacement*, so some appear twice and some not at all. Recompute the number. Do that
# thousands of times. The spread of the results approximates how much the number would move
# with a different sample. For two models we resample **items**, so both models are always
# scored on the same draw: a *paired* bootstrap.

# %%
# By hand: one resample of a 10-item toy, showing which items were drawn.
toy_ok = np.array([1, 1, 1, 0, 1, 1, 1, 1, 0, 1])
draw = rng.integers(0, len(toy_ok), len(toy_ok))
print("original accuracy:", toy_ok.mean())
print("one resample draws items", sorted(draw.tolist()), "-> accuracy", toy_ok[draw].mean())
boots = [toy_ok[rng.integers(0, 10, 10)].mean() for _ in range(5000)]
print(
    f"5,000 resamples: 95 % of them fall in [{np.percentile(boots, 2.5):.2f}, {np.percentile(boots, 97.5):.2f}]"
)

# %% [markdown]
# **On our data.** The paired bootstrap of (challenger − reference) accuracy.

# %%
ids = list(OK.index)
idx = rng.integers(0, len(ids), size=(10_000, len(ids)))
for m in ["typesafe/jev-1.13", "anthropic/claude-haiku-5.5", "openai/gpt-oss-20b"]:
    diff = OK.loc[ids, m].to_numpy(float) - OK.loc[ids, REF].to_numpy(float)
    bt = diff[idx].mean(axis=1)
    lo, hi = np.percentile(bt, [2.5, 97.5])
    print(f"{m:<30} difference {diff.mean():+.3f}, 95 % paired bootstrap [{lo:+.3f}, {hi:+.3f}]")

# %% [markdown]
# **What it means for us.** With very few disagreements, the bootstrap can draw an interval that
# excludes zero while McNemar's exact test is still not significant. The bootstrap is
# **optimistic when the evidence is a handful of items**. That is why rule E14 asks for both.
#
# **Check yourself.** Why must the resampling be paired, the same items for both models? *(Their
# errors are correlated: the hard items are hard for both. Resampling them separately would
# throw that away and make the interval too wide.)*

# %% [markdown]
# ---
# ## 6. How big a difference could we even see? The minimum detectable difference
#
# **The question.** Before comparing, ask: with this many items, what is the smallest real
# difference we would notice most of the time?
#
# **The intuition.** A test has **power**: the chance of noticing a difference that really
# exists. Small samples have little power, so small real differences go unnoticed. The minimum
# detectable difference (MDD) is the smallest true gap that a test would catch 80 % of the time
# at the 5 % level.


# %%
def power_two_prop(p1: float, p2: float, n: int, alpha: float = 0.05) -> float:
    pbar = (p1 + p2) / 2
    se0 = math.sqrt(2 * pbar * (1 - pbar) / n)
    se1 = math.sqrt(p1 * (1 - p1) / n + p2 * (1 - p2) / n)
    return float(stats.norm.cdf((abs(p1 - p2) - stats.norm.ppf(1 - alpha / 2) * se0) / se1))


def mdd(n: int, base: float = 0.95) -> float:
    return next(d / 1000 for d in range(1, 1000) if power_two_prop(base - d / 1000, base, n) >= 0.8)


for n_ in [28, 65, 109, 300, 1000]:
    print(f"N={n_:>5}: around 95 % accuracy, the minimum detectable difference is {mdd(n_):.3f}")
RESULTS["min_detectable_difference_n65"] = mdd(65, 0.85)

# %% [markdown]
# **What it means for us.** On the 65 scored line items, or on our 109 dev items, only large
# gaps are visible. Small real differences are invisible: hardening and growing the dev set is
# what buys resolution.
#
# **Check yourself.** Doubling N does not halve the MDD. Why? *(The standard error shrinks with
# √N, so halving the MDD takes about four times the items.)*

# %% [markdown]
# ---
# ## 7. "Not significantly worse" is not "as good": non-inferiority
#
# **The question.** Can we pick the cheapest model that is "not significantly worse" than the
# reference?
#
# **The intuition.** No. When the test has little power (section 6), almost nothing is
# significantly worse. The cheapest weak model passes simply because the sample is too small to
# convict it. That is exactly what happened in E13: the registered rule chose mistral-nemo.
# The fix is to **demand evidence of closeness**. Fix a margin δ in advance, and require the
# whole confidence interval of the difference to lie above −δ.
#
# **Simulation.** Two models whose true accuracies are 96 % and 92 % on 109 items, scored many
# times. How often does McNemar fail to call the weaker one worse?


# %%
def simulate(n: int, p_ref: float, p_weak: float, agree: float = 0.9, reps: int = 4000) -> float:
    misses = 0
    for _ in range(reps):
        base = rng.random(n)
        ref_ok = base < p_ref
        weak_ok = np.where(rng.random(n) < agree, base < p_weak, rng.random(n) < p_weak)
        bb = int((ref_ok & ~weak_ok).sum())
        cc = int((~ref_ok & weak_ok).sum())
        pv = stats.binomtest(min(bb, cc), bb + cc, 0.5).pvalue if bb + cc else 1.0
        misses += pv >= 0.05
    return misses / reps


share = simulate(N, 0.96, 0.92)
print(
    f"True gap of 4 points on {N} items: McNemar calls the weaker model 'not significantly worse' "
    f"in {share:.0%} of samples."
)

# %% [markdown]
# **What it means for us.** E14 replaces the flawed step. A model counts as "as good as" the
# reference only if the lower bound of its paired-bootstrap interval is above −2 points, and that
# rule was written before the next run. Here the fix was spotted because the result contradicted
# the accuracy table; the lesson is to write the margin into the rule from the start.

# %% [markdown]
# ---
# ## 8. Calibration: does "95 % sure" mean right 95 % of the time?
#
# **The question.** EXC-03 sends an item to review when the classifier is unsure. Can we trust
# the classifier's confidence number for that?
#
# **The intuition.** A calibrated model that says 0.9 is right about 90 % of the time on such
# items.
# - **Brier score:** the mean of (confidence − outcome)², where the outcome is 1 if right and
#   0 if wrong. Lower is better, and it rewards being both right and appropriately sure.
# - **ECE:** sort the items into confidence bins, then take the size-weighted average of
#   |accuracy − mean confidence| in each bin.
# - **Reliability diagram:** the same bins drawn as a chart.

# %%
# By hand: five items.
conf = np.array([0.9, 0.8, 0.95, 0.6, 0.99])
right = np.array([1, 1, 0, 1, 1])
sq = (conf - right) ** 2
print("squared gaps:", np.round(sq, 4).tolist())
print(f"Brier = mean = {sq.mean():.4f}")

# %% [markdown]
# **On our data.** Two kinds of confidence:
# - a generative model **writes** its confidence as a number;
# - a decision model **returns** a probability distribution, and we take the probability of
#   its chosen answer.


# %%
def calib(m: str) -> dict:
    g = P[(P["model"] == m)].dropna(subset=["confidence"])
    c = g["confidence"].astype(float).clip(0, 1).to_numpy()
    y = g["ok"].astype(float).to_numpy()
    bins = np.minimum((c * 10).astype(int), 9)
    filled = [k for k in range(10) if (bins == k).sum() >= 10]
    ece = sum(
        (bins == k).mean() * abs(y[bins == k].mean() - c[bins == k].mean())
        for k in range(10)
        if (bins == k).any()
    )
    return {
        "model": m,
        "brier": float(np.mean((c - y) ** 2)),
        "ece": float(ece),
        "mean_confidence": float(c.mean()),
        "accuracy": float(y.mean()),
        "bins_with_10plus_items": len(filled),
    }


CAL = pd.DataFrame([calib(m) for m in OK.columns]).set_index("model").sort_values("brier")
CAL.round(4)

# %% [markdown]
# **What it means for us.** Look at `bins_with_10plus_items`. When almost every answer sits in
# the top confidence bin, the data says little about calibration. A low Brier score there mostly
# reflects high accuracy. E14 therefore reports calibration only if at least three bins hold 10
# or more items. The EXC-03 threshold needs a dev set with genuinely uncertain items.
#
# **Check yourself.** A model that always says 0.5 and is right half the time: is it calibrated?
# Is it useful? *(It is calibrated, and useless for EXC-03, because it never separates easy items
# from hard ones.)*

# %% [markdown]
# ---
# ## 9. Base rate: what a flag means in production
#
# **The question.** On this dataset most receipts contain a violation. In a real expense stream
# a few percent do. What does that do to our false alarms?
#
# **The intuition.** With very few true violations, even a small false-alarm rate on the many
# clean receipts produces more false flags than true ones. **Positive predictive value (PPV)**
# = TP / (TP + FP) is the share of flags that are real.

# %%
N_, prev, sens, fpr = 10_000, 0.03, 15 / 16, 1 / 9
tp_ = N_ * prev * sens
fp_ = N_ * (1 - prev) * fpr
print(f"violations: {N_} x {prev} = {N_ * prev:.0f}; caught: x {sens:.4f} = {tp_:.2f}")
print(f"clean: {N_} x {1 - prev} = {N_ * (1 - prev):.0f}; falsely flagged: x {fpr:.4f} = {fp_:.2f}")
print(f"PPV = {tp_:.2f} / ({tp_:.2f} + {fp_:.2f}) = {tp_ / (tp_ + fp_):.4f}")
RESULTS["base_rate"] = {
    "receipts": N_,
    "prevalence": prev,
    "sensitivity": sens,
    "false_positive_rate": fpr,
    "true_positives": round(tp_, 2),
    "false_positives": round(fp_, 2),
    "ppv": round(tp_ / (tp_ + fp_), 4),
}

# %% [markdown]
# **What it means for us.** The false-positive rate measured on 9 clean receipts is both
# uncertain (section 1) and multiplied by thousands of clean receipts in production. Before
# trusting the system, it has to be measured on a large sample of mostly clean, real receipts.
#
# **Check yourself.** At what prevalence would half of all flags be real, with the same
# sensitivity and false-positive rate?

# %%
half = next(
    pv / 1000
    for pv in range(1, 1000)
    if (pv / 1000 * sens) / (pv / 1000 * sens + (1 - pv / 1000) * fpr) >= 0.5
)
print(f"about {half:.1%} prevalence")

# %% [markdown]
# ---
# ## 10. Selection bias: why we decide on dev and report on test once
#
# **The question.** We tried 15 models. Is the best score a fair estimate of the winner's real
# accuracy?
#
# **The intuition.** No. Picking the maximum of many noisy scores picks luck as well as skill.
# Even if every model were equally good, the best of 15 would look better than the truth.


# %%
def best_of(k: int, n: int, true_acc: float, reps: int = 4000) -> float:
    return float((rng.binomial(n, true_acc, size=(reps, k)) / n).max(axis=1).mean())


for k_ in [1, 5, 15, 40]:
    print(
        f"{k_:>2} equally good models (true 95 %) on {N} items: the best one scores {best_of(k_, N, 0.95):.3f} on average"
    )

# %% [markdown]
# **What it means for us.** The winner on the dev set is optimistic by construction. The 28 real
# receipts are run **once**, with the finalist only, and that number is what we report.
#
# **Check yourself.** Why not just choose on the 28 receipts? *(Then the reported number would
# carry the optimism above, and the choice would have looked at the answers.)*

# %% [markdown]
# ---
# ## 11. The disposition confusion matrix (brief, evaluation item 2)
#
# **The question.** For whole receipts, how often do we say flag, review or pass when the answer
# was something else?
#
# **The intuition.** Each row is the correct disposition and each column is ours. Two cells
# matter most:
# - **pass → flag or review:** a false alarm on a clean receipt;
# - **flag → pass or review:** a missed or downgraded violation.
#
# The table below is a toy with the brief's class sizes (9 pass, 16 flag, 3 review). The real
# one comes from `eval/` on the 28 receipts.

# %%
labels = ["flag", "review", "pass"]
cm = pd.DataFrame(
    [[14, 1, 1], [0, 2, 1], [1, 0, 8]],
    index=[f"true {x}" for x in labels],
    columns=[f"ours {x}" for x in labels],
)
print(
    "false alarms on clean receipts:",
    int(cm.loc["true pass", ["ours flag", "ours review"]].sum()),
    "of",
    int(cm.loc["true pass"].sum()),
)
print(
    "violations missed or downgraded:",
    int(cm.loc["true flag", ["ours review", "ours pass"]].sum()),
    "of",
    int(cm.loc["true flag"].sum()),
)
cm

# %%
(EXP / "results" / "04_results.json").write_text(json.dumps(RESULTS, indent=2))
print(json.dumps(RESULTS, indent=2))
