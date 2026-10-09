# %% [markdown]
# # 02 · Input EDA and a metadata retriever prototype
#
# **Inputs only.** Receipts are loaded through `explorations/lib/receipts_safe.py`, which deletes
# `labels`, `line_items[].labels` and `notes` right after `json.loads`. Nothing here reads,
# counts or summarises an answer, and nothing is evaluated against one.
#
# To keep this notebook safe to share, raw item descriptions are never printed in full: only
# their language, length and counts.

# %%
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

REPO = next(p for p in [Path.cwd(), *Path.cwd().parents] if (p / "data" / "policy-docs").is_dir())
EXP = REPO / "explorations"
sys.path.insert(0, str(EXP / "lib"))
from receipts_safe import assert_clean, load_inputs

receipts = load_inputs()
assert_clean(receipts)
print(
    f"{len(receipts)} receipts, {sum(len(r['line_items']) for r in receipts)} line items; answer keys removed"
)
print("receipt fields:", sorted(receipts[0]))
print("line fields:", sorted(receipts[0]["line_items"][0]))

# %%
R = pd.DataFrame([{k: v for k, v in r.items() if k != "line_items"} for r in receipts])
R["n_items"] = [len(r["line_items"]) for r in receipts]
R["dt"] = pd.to_datetime(R["transaction_datetime"])
R["date"] = R["dt"].dt.date
L = pd.DataFrame(
    [
        {
            "receipt_id": r["receipt_id"],
            **{k: v for k, v in i.items() if k != "description_raw"},
            "desc_len": len(i["description_raw"]),
        }
        for r in receipts
        for i in r["line_items"]
    ]
)
R.drop(columns=["dt"]).head(3)

# %% [markdown]
# ## Entity, country, currency and FX

# %%
fig, axes = plt.subplots(1, 3, figsize=(14, 3.2))
R["entity"].value_counts().plot.bar(ax=axes[0], title="entity")
R["employee_country"].value_counts().plot.bar(ax=axes[1], title="employee_country")
R["currency"].value_counts().plot.bar(ax=axes[2], title="currency")
plt.tight_layout()
pd.crosstab(R["entity"], R["currency"])

# %%
fx = R.groupby("currency")["fx_rate_to_usd"].agg(["count", "min", "max", "nunique"])
print("FX rate per currency (rate multiplies the receipt amount into USD):")
fx

# %%
# Consistency of the conversion: total_amount * fx_rate_to_usd versus total_amount_usd.
R["usd_check"] = (R["total_amount"] * R["fx_rate_to_usd"] - R["total_amount_usd"]).abs()
print("max |total * rate - total_usd|:", round(R["usd_check"].max(), 4))
L["line_check"] = (L["quantity"] * L["unit_price"] - L["amount"]).abs()
print("max |qty * unit_price - amount|:", round(L["line_check"].max(), 4))
sums = L.groupby("receipt_id")["amount"].sum()
R["items_minus_total"] = R["receipt_id"].map(sums) - R["total_amount"]
print(
    "receipts whose line amounts do not add up to the total:",
    int((R["items_minus_total"].abs() > 0.01).sum()),
)

# %% [markdown]
# ## Expense type, MCC and risk tier
#
# The risk tier comes from the table in `merchant-category-risk.md`, parsed here. Any MCC not in
# the table is low risk.

# %%
mcc_text = (REPO / "data" / "policy-docs" / "merchant-category-risk.md").read_text()
MCC_TIER = {
    int(m): t.strip("* ").lower()
    for m, t in re.findall(r"^\| (\d{4}) \| [^|]+ \| ([^|]+) \|", mcc_text, re.M)
}
R["mcc_tier"] = R["mcc"].map(lambda m: MCC_TIER.get(int(m), "low (unlisted)"))
pd.crosstab(R["submitted_expense_type"], R["mcc_tier"], margins=True)

# %%
R.groupby(["mcc", "mcc_description", "mcc_tier"]).size().rename("receipts").reset_index()

# %% [markdown]
# ## Itemization, attendees, trips, approval references

# %%
print("itemized:", R["itemized"].value_counts(dropna=False).to_dict())
print("attendee_count:", R["attendee_count"].value_counts(dropna=False).sort_index().to_dict())
print("receipts linked to a trip:", int(R["trip_id"].notna().sum()), "of", len(R))
print("trip_nights:", R["trip_nights"].value_counts(dropna=False).sort_index().to_dict())
refs = R["pre_approval_ref"].dropna()
print(
    "approval references recorded:",
    len(refs),
    "| formats:",
    Counter(re.sub(r"\d", "9", x) for x in refs),
)

# %%
pd.crosstab(
    R["submitted_expense_type"],
    R["attendee_count"].fillna(-1).astype(int).rename("attendees (-1 = null)"),
)

# %% [markdown]
# ## Line items: languages, items per receipt, amounts

# %%
fig, axes = plt.subplots(1, 3, figsize=(14, 3.2))
L["language"].value_counts().plot.bar(ax=axes[0], title="item language")
R["n_items"].value_counts().sort_index().plot.bar(ax=axes[1], title="items per receipt")
R["total_amount_usd"].plot.hist(bins=20, ax=axes[2], title="receipt total (USD)")
plt.tight_layout()
print("description length (characters):", L["desc_len"].describe().round(1).to_dict())

# %%
print("receipt total USD:", R["total_amount_usd"].describe().round(2).to_dict())
print("line amount USD:", L["amount_usd"].describe().round(2).to_dict())
pd.crosstab(L.merge(R[["receipt_id", "currency"]], on="receipt_id")["currency"], L["language"])

# %% [markdown]
# ## Cross-receipt groupings that MEAL-01 / REG-02 / REG-03, HEALTH-01 and TIME-03 need
#
# - **Employee and calendar date** for the daily meal caps (MEAL-01, REG-02, REG-03): every meal
#   receipt of one employee on the same date is summed per person.
# - **Trip** for HEALTH-01 (OTC medication up to $25 across all of a trip's receipts).
# - **Employee, merchant name and date** for TIME-03 (split transactions).

# %%
MEAL_TYPES = {"Meals - Individual", "Meals - Team", "Client Entertainment"}
R["is_meal_type"] = R["submitted_expense_type"].isin(MEAL_TYPES)
day = (
    R[R["is_meal_type"]]
    .groupby(["employee_id", "date"])
    .agg(receipts=("receipt_id", "count"), ids=("receipt_id", list))
)
print(
    "employee-days with meal-type receipts:",
    len(day),
    "| with more than one receipt:",
    int((day["receipts"] > 1).sum()),
)
day[day["receipts"] > 1]

# %%
trips = (
    R[R["trip_id"].notna()]
    .groupby("trip_id")
    .agg(
        receipts=("receipt_id", "count"),
        nights=("trip_nights", "first"),
        employees=("employee_id", "nunique"),
        ids=("receipt_id", list),
    )
)
print(
    "trips:", len(trips), "| trips with more than one receipt:", int((trips["receipts"] > 1).sum())
)
trips.sort_values("receipts", ascending=False).head(10)

# %%
split = R.groupby(["employee_id", "merchant_name", "date"]).agg(
    receipts=("receipt_id", "count"), ids=("receipt_id", list)
)
split[split["receipts"] > 1]

# %% [markdown]
# ## Domestic or international, and the euro-rate question
#
# MEAL-01 needs the currency of the employee's home country. The data has no such field, so this
# is an explicit table for the countries present. REG-03 and REG-04 need the euro rate on the
# transaction date; for a non-EUR receipt of an EMEA employee that rate is not on the record
# (ambiguity 1 in `policy_ambiguities.yaml`). This counts how often that happens.

# %%
HOME_CCY = {
    "US": "USD",
    "IN": "INR",
    "JP": "JPY",
    "SG": "SGD",
    "GB": "GBP",
    "DE": "EUR",
    "FR": "EUR",
    "NL": "EUR",
    "IE": "EUR",
    "PT": "EUR",
    "ES": "EUR",
    "CA": "CAD",
    "MX": "MXN",
    "BR": "BRL",
}
unknown = sorted(set(R["employee_country"]) - set(HOME_CCY))
print("countries without a home currency in the table:", unknown or "none")
R["home_ccy"] = R["employee_country"].map(HOME_CCY)
R["international"] = R["currency"] != R["home_ccy"]
print(pd.crosstab(R["entity"], R["international"]).to_string())
emea_non_eur = R[(R["entity"] == "EMEA") & (R["currency"] != "EUR")]
eur_dates = set(R.loc[R["currency"] == "EUR", "date"])
print(
    "EMEA receipts not in EUR:",
    len(emea_non_eur),
    "| of those, with a EUR receipt on the same date to borrow the rate from:",
    int(emea_non_eur["date"].isin(eur_dates).sum()),
)

# %% [markdown]
# ## Metadata retriever prototype
#
# Deterministic: which rules **could** apply to a receipt, from its metadata alone, before any
# item is classified. Two layers:
#
# 1. **Receipt-level triggers** that need no item categories (MCC tier, itemization, currency,
#    entity, trip, time, attendee count, cross-receipt groups).
# 2. **Item-rule priors**: item-category rules that the merchant (MCC) or the declared expense type
#    make plausible. After classification the engine adds any item rule whose category actually
#    appears, so these priors only decide what is worth checking first; they never remove a rule
#    the classified items trigger.
#
# The goal is recall: a missing rule is a missed violation, an extra rule only costs a check.
# There is **no evaluation here**; whether it ever misses a rule is measured later, in `eval/`.

# %%
ON_PREMISES = {5812, 5813, 7011}
HIGH = {m for m, t in MCC_TIER.items() if t == "high"}
MEDIUM = {m for m, t in MCC_TIER.items() if t == "medium"}
ALCOHOL_RULES = ["ALC-01", "ALC-02", "ALC-03"]

MCC_PRIORS = {
    5921: ["ALC-03"],
    5993: ["PERS-03"],
    7995: ["ENT-02"],
    7297: ["PERS-01"],
    5944: ["GIFT-01", "GIFT-04"],
    5813: ["ALC-01", "ALC-02"],
    5812: ["ALC-01", "ALC-02", "GIFT-04"],
    7011: ["ALC-01", "ALC-02", "LAUNDRY-01", "PERS-01"],
    5912: ["HEALTH-01", "PERS-01", "HOUSE-01"],
    5311: ["PERS-02", "HOUSE-01", "TECH-01", "GIFT-01", "PERS-01"],
    5411: ["ALC-03", "HOUSE-01", "PERS-01", "HEALTH-01"],
    5732: ["TECH-01", "TECH-02", "TECH-03"],
    5942: ["GIFT-01"],
    5943: ["TECH-02", "HOUSE-01"],
    5734: ["TECH-04"],
    7216: ["LAUNDRY-01"],
}
TYPE_PRIORS = {
    "Client Gifts": ["GIFT-01", "GIFT-02", "GIFT-03", "GIFT-04"],
    "Client Entertainment": ["ALC-01", "ALC-02", "ENT-01", "GIFT-04"],
    "Meals - Team": ["ALC-01", "ALC-02"],
    "Meals - Individual": ["ALC-01"],
    "Computer Equipment": ["TECH-01", "TECH-02", "TECH-03"],
    "Office Supplies": ["TECH-02", "HOUSE-01"],
    "Software": ["TECH-04"],
    "Lodging": ["LAUNDRY-01", "PERS-01"],
    "Travel - Other": ["HEALTH-01", "LAUNDRY-01", "PERS-01", "PERS-02"],
}
TIME_TYPES = {"Meals - Individual", "Lodging", "Travel - Other"}

group_size = R.groupby(["employee_id", "merchant_name", "date"])["receipt_id"].transform("count")
R["split_group"] = group_size


def eur_to_usd_rate(r) -> float | None:
    if r["currency"] == "EUR":
        return r["fx_rate_to_usd"]
    same_day = R[(R["currency"] == "EUR") & (R["date"] == r["date"])]["fx_rate_to_usd"]
    return float(same_day.iloc[0]) if len(same_day) else None


def candidates(r) -> list[str]:
    out: set[str] = set()
    mcc = int(r["mcc"])
    apac, emea = r["entity"] == "APAC", r["entity"] == "EMEA"
    meal = r["submitted_expense_type"] in MEAL_TYPES
    # Receipt-level triggers.
    if mcc in HIGH:
        out.add("MCC-01")
    if mcc in MEDIUM:
        out.add("MCC-02")
    if mcc == 5813:
        out.add("MCC-03")
    if meal:
        out.add("REG-02" if apac else "REG-03" if emea else "MEAL-01")
        if r["total_amount_usd"] > 150:
            out.add("MEAL-02")
    if not r["itemized"] and r["total_amount_usd"] > 75:
        out.add("DOC-01")
    if not (r["merchant_name"] and r["transaction_datetime"] and r["total_amount"] is not None):
        out.add("DOC-02")
    if r["itemized"]:
        out.add("DOC-03")
    if r["currency"] != "USD":
        out.add("DOC-04")
    if emea:
        rate = eur_to_usd_rate(r)
        # Above EUR 50, or unknown euro rate: keep the rule (recall first).
        if rate is None or r["total_amount_usd"] > 50 * rate:
            out.add("REG-04")
    if r["dt"].hour < 5:
        out.add("TIME-01")
    if r["submitted_expense_type"] in TIME_TYPES and pd.isna(r["trip_id"]):
        out.add("TIME-02")
    if r["split_group"] > 1:
        out.add("TIME-03")
    # Item-rule priors.
    out |= set(MCC_PRIORS.get(mcc, []))
    out |= set(TYPE_PRIORS.get(r["submitted_expense_type"], []))
    # Alcohol scope: on-premises merchants get ALC-01/02, others ALC-03; APAC gets REG-01 instead.
    if out & set(ALCOHOL_RULES) or meal:
        out -= set(ALCOHOL_RULES)
        if apac:
            out.add("REG-01")
        elif mcc in ON_PREMISES:
            out |= {"ALC-01", "ALC-02"}
        else:
            out.add("ALC-03")
    if apac and mcc == 5921:
        out.add("REG-01")
    return sorted(out)


R["candidates"] = R.apply(candidates, axis=1)
R["n_candidates"] = R["candidates"].map(len)
cand = dict(zip(R["receipt_id"], R["candidates"]))
(EXP / "policy" / "02_retriever_candidates.json").write_text(
    json.dumps(cand, indent=1, sort_keys=True)
)
print(
    f"{len(cand)} receipts; candidates per receipt: mean {R['n_candidates'].mean():.1f}, "
    f"min {R['n_candidates'].min()}, max {R['n_candidates'].max()} (of 41 rules)"
)
R[["receipt_id", "entity", "submitted_expense_type", "mcc", "n_candidates", "candidates"]]

# %%
rule_freq = Counter(r for c in cand.values() for r in c)
pd.Series(rule_freq).sort_values().plot.barh(
    figsize=(6, 7), title="receipts on which each rule is a candidate"
)
plt.tight_layout()

# %% [markdown]
# ## What this shows
#
# - The receipt-level rules are fully decidable from metadata; the retriever only narrows the
#   **item** rules, and the engine still adds any item rule whose category the classifier
#   returns. That keeps the retriever from ever being the cause of a missed violation on its own.
# - The cross-receipt groupings above are what the engine must compute before applying the daily
#   meal caps, HEALTH-01 and TIME-03; they are part of the engine, not of the classifier.
# - The euro-rate gap for non-EUR EMEA receipts is real in this data whenever the count above is
#   non-zero; it needs Luis's decision (ambiguity 1).
