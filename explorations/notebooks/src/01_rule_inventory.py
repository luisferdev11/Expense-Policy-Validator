# %% [markdown]
# # 01 · Rule inventory
#
# Builds `rules_draft.yaml` (the 41 rules, one structured record each) and
# `policy_ambiguities.yaml` from `data/policy-docs/` only. No receipt is read here.
#
# How it works:
#
# 1. Rule IDs and the file that defines each one are **parsed from the policy text** (a rule is
#    defined where its ID first appears in bold).
# 2. `literal_text` is **extracted by code**: the paragraph that starts at the bold rule ID,
#    with the Markdown bold markers removed. Nothing is typed by hand, and every quote is checked
#    against its source file below.
# 3. The structured fields (severity, scope, triggers, required fields, thresholds, carve-outs,
#    replaces) are my reading of the policy text, written as a Python table. They are a **DRAFT**
#    for Luis to verify.

# %%
from __future__ import annotations

import re
from pathlib import Path

import pandas as pd
import yaml

REPO = next(p for p in [Path.cwd(), *Path.cwd().parents] if (p / "data" / "policy-docs").is_dir())
EXP = REPO / "explorations"
DOCS = {p.name: p.read_text() for p in sorted((REPO / "data" / "policy-docs").glob("*.md"))}


def norm(s: str) -> str:
    s = s.lower()
    s = re.sub(r"[*`«»\"“”‘’]", "", s)
    return re.sub(r"\s+", " ", s).strip()


def defined_in() -> dict[str, str]:
    out: dict[str, str] = {}
    for name, text in DOCS.items():
        for m in re.finditer(r"\*\*([A-Z]+-\d{2})\b", text):
            out.setdefault(m.group(1), name)
    return out


RULE_DOC = defined_in()
print(f"{len(RULE_DOC)} rule IDs found in {len(DOCS)} policy documents")
pd.Series(RULE_DOC).value_counts().rename("rules per document")

# %% [markdown]
# ## Extracting the literal text of each rule
#
# The paragraph starts at `**RULE-ID` and ends at the first blank line. Bold markers are removed,
# line breaks inside the paragraph collapsed to spaces. The checker-style comparison (lowercase,
# markup removed, whitespace collapsed) must find it inside the defining document.


# %%
def rule_paragraph(rid: str) -> str:
    text = DOCS[RULE_DOC[rid]]
    start = text.index(f"**{rid}")
    end = text.find("\n\n", start)
    para = text[start : end if end != -1 else len(text)]
    para = para.replace("**", "")
    return re.sub(r"\s+", " ", para).strip()


LITERAL = {rid: rule_paragraph(rid) for rid in RULE_DOC}
bad = [rid for rid, lit in LITERAL.items() if norm(lit) not in norm(DOCS[RULE_DOC[rid]])]
short = [rid for rid, lit in LITERAL.items() if len(lit.split()) < 8]
print("not verbatim:", bad or "none", "| shorter than 8 words:", short or "none")

# %% [markdown]
# ## Structured reading of each rule (DRAFT)
#
# Conventions:
#
# - `severity`: the severity the policy states; `review_signal` for rules that only raise a review
#   signal; `none` for rules that raise nothing on their own (definitions, procedures);
#   a mapping when it is conditional (HEALTH-01).
# - `scope`: `receipt` when the policy says the rule cites no line items (EXC-04 list, plus the
#   receipt-level review signals), `line_items` when it cites the items that break it, `none` for
#   rules that never produce a finding of their own.
# - `thresholds`: always in USD after conversion at the receipt's own rate (DOC-04, REG-05),
#   except the two EUR figures, which are converted at the euro rate on the transaction date.
# - `carve_outs`: what has to be recorded for the rule not to fire, and the **kind** of approval
#   reference it accepts (EXC-02). A reference of the wrong kind does not count.
# - `replaces`: rules this rule is reported instead of, where both would otherwise fire.

# %%
USD_RATE = "converted to USD with fx_rate_to_usd on the receipt (REG-05)"
EUR_RATE = "EUR converted to USD at the euro rate on the transaction date (receipt's own rate for EUR receipts)"

SPEC: dict[str, dict] = {
    "EXC-01": dict(
        severity="none",
        scope="none",
        triggers=["disposition = f(max severity of exceptions, any review signal)"],
        required_fields=["exceptions[].severity", "review_signals"],
        thresholds=[],
        carve_outs=[],
        replaces=[],
        notes="critical|high|medium -> flag; low only or signals only -> review; none -> pass.",
    ),
    "EXC-02": dict(
        severity="none",
        scope="none",
        triggers=["rule requires a reference -> check pre_approval_ref and its kind"],
        required_fields=["pre_approval_ref"],
        thresholds=[],
        carve_outs=[
            {"rule": "TECH-02", "reference_kind": "pre-approval"},
            {"rule": "ENT-01", "reference_kind": "VP approval"},
            {"rule": "TECH-04", "reference_kind": "manager approval"},
            {"rule": "PERS-01", "reference_kind": "baggage-delay reference"},
            {"rule": "PERS-02", "reference_kind": "baggage-delay reference"},
        ],
        replaces=[],
        notes="Reference waives nothing else. Data: every ref is PA- (pre-approval kind).",
    ),
    "EXC-03": dict(
        severity="review_signal",
        scope="line_items",
        triggers=["item.confidence < CONF_THRESHOLD"],
        required_fields=["line_items[].confidence"],
        thresholds=[{"value": "unspecified", "unit": "classifier confidence", "basis": "per item"}],
        carve_outs=[
            {"condition": "non-itemized charge is `other`, never uncertain", "reference_kind": None}
        ],
        replaces=[],
        notes="Uncertain line excluded from every other rule on the receipt.",
    ),
    "EXC-04": dict(
        severity="none",
        scope="none",
        triggers=["every exception emitted"],
        required_fields=["rule_id", "policy_doc", "line_ids"],
        thresholds=[],
        carve_outs=[],
        replaces=[],
        notes="Item rules: line_ids = offending lines, never service_fee. Receipt rules: line_ids = []. One per rule per receipt.",
    ),
    "GIFT-01": dict(
        severity="medium",
        scope="line_items",
        triggers=[
            'is_gift(line) := type == "Client Gifts" or line names a recipient',
            "sum(amount_usd of gift lines with same recipient) > 50",
            "is_gift(line) and line.amount_usd >= 10 and recipient unnamed",
        ],
        required_fields=[
            "submitted_expense_type",
            "line_items[].description_raw",
            "line_items[].amount_usd",
            "line_items[].category",
        ],
        thresholds=[
            {
                "value": 50,
                "unit": "USD",
                "basis": "per recipient per receipt (occasion)",
                "conversion": USD_RATE,
            },
            {
                "value": 10,
                "unit": "USD",
                "basis": "per line, named-recipient test",
                "conversion": USD_RATE,
            },
        ],
        carve_outs=[
            {
                "condition": "cards and small tokens under $10 need no named recipient",
                "reference_kind": None,
            },
            {
                "condition": "gift cards and cash equivalents go to GIFT-02 alone",
                "reference_kind": None,
            },
            {
                "condition": "food, drink and gratuities consumed at a meal are not gifts",
                "reference_kind": None,
            },
        ],
        replaces=[],
    ),
    "GIFT-02": dict(
        severity="high",
        scope="line_items",
        triggers=["line.category == gift_card"],
        required_fields=["line_items[].category"],
        thresholds=[],
        carve_outs=[],
        replaces=["GIFT-01"],
        notes="gift_card lines skip GIFT-01.",
    ),
    "GIFT-03": dict(
        severity="medium",
        scope="line_items",
        triggers=["line is an employee recognition gift or award"],
        required_fields=["line_items[].description_raw", "line_items[].category"],
        thresholds=[],
        carve_outs=[],
        replaces=[],
    ),
    "GIFT-04": dict(
        severity="critical",
        scope="line_items",
        triggers=[
            "line provided to recipient in {government official, public employee, SOE employee}"
        ],
        required_fields=["line_items[].description_raw"],
        thresholds=[{"value": 0, "unit": "USD", "basis": "any amount"}],
        carve_outs=[
            {"condition": "gratuity lines are never cited (EXC-04)", "reference_kind": None}
        ],
        replaces=["GIFT-01"],
        notes="line_ids include the official's meal line (employee share too), never service_fee. Meal caps still evaluated.",
    ),
    "MEAL-01": dict(
        severity="medium",
        scope="receipt",
        triggers=[
            "is_meal_receipt := type in MEAL_TYPES and (has food_beverage/alcohol line or not itemized)",
            "entity == GLOBAL and sum over (employee_id, date) of meal_spend / persons > cap(day)",
        ],
        required_fields=[
            "employee_id",
            "transaction_datetime",
            "submitted_expense_type",
            "currency",
            "employee_country",
            "attendee_count",
            "line_items[].category",
            "line_items[].amount_usd",
            "total_amount_usd",
            "itemized",
        ],
        thresholds=[
            {
                "value": 75,
                "unit": "USD",
                "basis": "per person per day, domestic",
                "conversion": USD_RATE,
            },
            {
                "value": 100,
                "unit": "USD",
                "basis": "per person per day, international (receipt currency differs from home-country currency); the higher cap on a mixed day",
                "conversion": USD_RATE,
            },
        ],
        carve_outs=[],
        replaces=[],
        notes="Emit on each contributing meal receipt of the breached day. APAC -> REG-02, EMEA -> REG-03.",
    ),
    "MEAL-02": dict(
        severity="low",
        scope="receipt",
        triggers=["is_meal_receipt and total_amount_usd > 150 and attendee_count is null"],
        required_fields=["submitted_expense_type", "total_amount_usd", "attendee_count"],
        thresholds=[
            {"value": 150, "unit": "USD", "basis": "receipt total", "conversion": USD_RATE}
        ],
        carve_outs=[],
        replaces=[],
    ),
    "ALC-01": dict(
        severity="high",
        scope="line_items",
        triggers=[
            'line.category == alcohol and mcc in {5812, 5813, 7011} and not (type == "Client Entertainment" and attendee_count >= 2)'
        ],
        required_fields=[
            "mcc",
            "submitted_expense_type",
            "attendee_count",
            "line_items[].category",
        ],
        thresholds=[
            {
                "value": 2,
                "unit": "attendees",
                "basis": "minimum attendee count, including the employee",
            }
        ],
        carve_outs=[
            {
                "condition": "declared Client Entertainment with attendee_count >= 2",
                "reference_kind": None,
            }
        ],
        replaces=[],
    ),
    "ALC-02": dict(
        severity="medium",
        scope="line_items",
        triggers=["ALC-01 satisfied and sum(alcohol amount_usd) / attendee_count > 30"],
        required_fields=["attendee_count", "line_items[].category", "line_items[].amount_usd"],
        thresholds=[
            {
                "value": 30,
                "unit": "USD",
                "basis": "per attendee, alcohol lines only",
                "conversion": USD_RATE,
            }
        ],
        carve_outs=[],
        replaces=[],
    ),
    "ALC-03": dict(
        severity="high",
        scope="line_items",
        triggers=["line.category == alcohol and mcc not in {5812, 5813, 7011}"],
        required_fields=["mcc", "line_items[].category"],
        thresholds=[],
        carve_outs=[],
        replaces=[],
        notes="Context irrelevant. mcc 5921 -> MCC-01 as well.",
    ),
    "ENT-01": dict(
        severity="medium",
        scope="line_items",
        triggers=[
            "line is venue spend (golf, sport, theatre, concert, similar) and ref kind != VP approval"
        ],
        required_fields=["line_items[].description_raw", "mcc", "pre_approval_ref"],
        thresholds=[],
        carve_outs=[{"condition": "VP approval recorded", "reference_kind": "VP approval"}],
        replaces=[],
        notes="Tickets: no taxonomy category -> other.",
    ),
    "ENT-02": dict(
        severity="high",
        scope="line_items",
        triggers=["line.category == gambling"],
        required_fields=["line_items[].category"],
        thresholds=[],
        carve_outs=[],
        replaces=[],
    ),
    "MCC-01": dict(
        severity="high",
        scope="receipt",
        triggers=["mcc in {5921, 5993, 7995, 7297, 5944}"],
        required_fields=["mcc"],
        thresholds=[],
        carve_outs=[],
        replaces=[],
        notes="Independent of lines; APAC keeps it next to REG-01.",
    ),
    "MCC-02": dict(
        severity="review_signal",
        scope="receipt",
        triggers=["mcc in {5813, 5912, 5311, 5411, 5732}"],
        required_fields=["mcc"],
        thresholds=[],
        carve_outs=[],
        replaces=[],
        notes="Signal only; emitted next to any exceptions.",
    ),
    "MCC-03": dict(
        severity="none",
        scope="none",
        triggers=["mcc == 5813 -> treat as on-premises for ALC-01/ALC-02"],
        required_fields=["mcc"],
        thresholds=[],
        carve_outs=[],
        replaces=[],
        notes="5813 on-premises: ALC-01/ALC-02, never ALC-03.",
    ),
    "PERS-01": dict(
        severity="medium",
        scope="line_items",
        triggers=["line.category == personal_care and not baggage_delay_allowance_applies"],
        required_fields=["line_items[].category", "pre_approval_ref"],
        thresholds=[
            {
                "value": 150,
                "unit": "USD",
                "basis": "baggage-delay allowance, shared with PERS-02, per delay",
                "conversion": USD_RATE,
            }
        ],
        carve_outs=[
            {
                "condition": "checked baggage delayed more than 24 hours: essential toiletries up to $150",
                "reference_kind": "baggage-delay reference",
            }
        ],
        replaces=[],
    ),
    "PERS-02": dict(
        severity="medium",
        scope="line_items",
        triggers=["line.category == clothing and not baggage_delay_allowance_applies"],
        required_fields=["line_items[].category", "pre_approval_ref"],
        thresholds=[
            {
                "value": 150,
                "unit": "USD",
                "basis": "baggage-delay allowance, shared with PERS-01, per delay",
                "conversion": USD_RATE,
            }
        ],
        carve_outs=[
            {
                "condition": "baggage delayed more than 24 hours, one shared $150 allowance",
                "reference_kind": "baggage-delay reference",
            }
        ],
        replaces=[],
    ),
    "PERS-03": dict(
        severity="high",
        scope="line_items",
        triggers=["line.category == tobacco"],
        required_fields=["line_items[].category"],
        thresholds=[],
        carve_outs=[],
        replaces=[],
    ),
    "HOUSE-01": dict(
        severity="medium",
        scope="line_items",
        triggers=["line.category == household_goods"],
        required_fields=["line_items[].category"],
        thresholds=[],
        carve_outs=[],
        replaces=[],
    ),
    "HEALTH-01": dict(
        severity={"otc_medication": "low", "prescription_medication": "medium"},
        scope="line_items",
        triggers=[
            "line.category == health_otc and trip_id is null",
            "line.category == health_otc and sum(health_otc amount_usd over trip_id) > 25",
            "line is prescription medication (category other) -> medium",
        ],
        required_fields=[
            "trip_id",
            "line_items[].category",
            "line_items[].amount_usd",
            "line_items[].description_raw",
        ],
        thresholds=[
            {
                "value": 25,
                "unit": "USD",
                "basis": "OTC total per trip, across receipts",
                "conversion": USD_RATE,
            }
        ],
        carve_outs=[
            {
                "condition": "OTC medication on a trip-linked receipt within the $25 trip total",
                "reference_kind": None,
            }
        ],
        replaces=[],
    ),
    "LAUNDRY-01": dict(
        severity="low",
        scope="line_items",
        triggers=["line.category == laundry_service and (trip_id is null or trip_nights < 4)"],
        required_fields=["trip_id", "trip_nights", "line_items[].category"],
        thresholds=[
            {"value": 4, "unit": "nights", "basis": "minimum trip length, from the receipt"}
        ],
        carve_outs=[{"condition": "trip of four or more nights", "reference_kind": None}],
        replaces=[],
    ),
    "DOC-01": dict(
        severity="medium",
        scope="receipt",
        triggers=["not itemized and total_amount_usd > 75"],
        required_fields=["itemized", "total_amount_usd"],
        thresholds=[{"value": 75, "unit": "USD", "basis": "receipt total", "conversion": USD_RATE}],
        carve_outs=[],
        replaces=[],
    ),
    "DOC-02": dict(
        severity="medium",
        scope="receipt",
        triggers=["merchant_name or transaction_datetime or total_amount missing"],
        required_fields=["merchant_name", "transaction_datetime", "total_amount"],
        thresholds=[],
        carve_outs=[],
        replaces=[],
    ),
    "DOC-03": dict(
        severity="medium",
        scope="receipt",
        triggers=[
            "kept := lines minus {service_fee, other}; kept non-empty and no kept.category in COVERS[type]"
        ],
        required_fields=["submitted_expense_type", "line_items[].category"],
        thresholds=[],
        carve_outs=[
            {
                "condition": "no items left after removing service fees, gratuities and `other`: DOC-03 does not apply",
                "reference_kind": None,
            }
        ],
        replaces=[],
        notes="Additive: emitted next to item-rule exceptions.",
    ),
    "DOC-04": dict(
        severity="medium",
        scope="receipt",
        triggers=["currency != USD and (currency missing or fx_rate_to_usd missing)"],
        required_fields=["currency", "fx_rate_to_usd"],
        thresholds=[],
        carve_outs=[],
        replaces=[],
    ),
    "REG-01": dict(
        severity="high",
        scope="line_items",
        triggers=["entity == APAC and line.category == alcohol"],
        required_fields=["entity", "employee_country", "line_items[].category"],
        thresholds=[],
        carve_outs=[],
        replaces=["ALC-01", "ALC-02", "ALC-03"],
        notes="MCC-01 unaffected.",
    ),
    "REG-02": dict(
        severity="medium",
        scope="receipt",
        triggers=["entity == APAC and per-person meal spend per (employee_id, date) > 60"],
        required_fields=[
            "entity",
            "employee_id",
            "transaction_datetime",
            "attendee_count",
            "line_items[].category",
            "line_items[].amount_usd",
        ],
        thresholds=[
            {"value": 60, "unit": "USD", "basis": "per person per day", "conversion": USD_RATE}
        ],
        carve_outs=[],
        replaces=["MEAL-01"],
    ),
    "REG-03": dict(
        severity="medium",
        scope="receipt",
        triggers=[
            "entity == EMEA and per-person meal spend per (employee_id, date) > 70 * eur_usd(date)"
        ],
        required_fields=[
            "entity",
            "employee_id",
            "transaction_datetime",
            "currency",
            "fx_rate_to_usd",
            "attendee_count",
            "line_items[].category",
            "line_items[].amount_usd",
        ],
        thresholds=[
            {"value": 70, "unit": "EUR", "basis": "per person per day", "conversion": EUR_RATE}
        ],
        carve_outs=[],
        replaces=["MEAL-01"],
    ),
    "REG-04": dict(
        severity="low",
        scope="receipt",
        triggers=[
            "entity == EMEA and total_amount_usd > 50 * eur_usd(date) and vat_number is null"
        ],
        required_fields=["entity", "total_amount", "currency", "fx_rate_to_usd"],
        thresholds=[{"value": 50, "unit": "EUR", "basis": "receipt total", "conversion": EUR_RATE}],
        carve_outs=[],
        replaces=[],
    ),
    "REG-05": dict(
        severity="none",
        scope="none",
        triggers=["any comparison of a non-USD amount with a threshold"],
        required_fields=["fx_rate_to_usd", "transaction_datetime"],
        thresholds=[],
        carve_outs=[],
        replaces=[],
        notes="Rate definition; missing rate -> DOC-04.",
    ),
    "TECH-01": dict(
        severity="high",
        scope="line_items",
        triggers=["line.category == personal_electronics"],
        required_fields=["line_items[].category"],
        thresholds=[],
        carve_outs=[],
        replaces=[],
        notes="Purpose irrelevant; Computer Equipment declaration still fires.",
    ),
    "TECH-02": dict(
        severity="medium",
        scope="line_items",
        triggers=[
            "line.category == computer_accessory and unit_price * fx_rate_to_usd > 200 and ref kind != pre-approval"
        ],
        required_fields=[
            "line_items[].category",
            "line_items[].unit_price",
            "fx_rate_to_usd",
            "pre_approval_ref",
        ],
        thresholds=[
            {
                "value": 200,
                "unit": "USD",
                "basis": "unit price per item, not line total",
                "conversion": USD_RATE,
            }
        ],
        carve_outs=[
            {"condition": "pre-approval reference recorded", "reference_kind": "pre-approval"}
        ],
        replaces=[],
    ),
    "TECH-03": dict(
        severity="high",
        scope="line_items",
        triggers=["line is mobile phone hardware (category other)"],
        required_fields=["line_items[].description_raw", "line_items[].category"],
        thresholds=[],
        carve_outs=[],
        replaces=[],
    ),
    "TECH-04": dict(
        severity="low",
        scope="line_items",
        triggers=["line.category == software_subscription and ref kind != manager approval"],
        required_fields=["line_items[].category", "pre_approval_ref"],
        thresholds=[],
        carve_outs=[
            {"condition": "manager approval recorded", "reference_kind": "manager approval"}
        ],
        replaces=[],
    ),
    "TIME-01": dict(
        severity="review_signal",
        scope="receipt",
        triggers=["time(transaction_datetime) in [00:00, 05:00)"],
        required_fields=["transaction_datetime"],
        thresholds=[{"value": "00:00-05:00", "unit": "local time", "basis": "half-open interval"}],
        carve_outs=[],
        replaces=[],
    ),
    "TIME-02": dict(
        severity="review_signal",
        scope="receipt",
        triggers=["type in {Meals - Individual, Lodging, Travel - Other} and trip_id is null"],
        required_fields=["submitted_expense_type", "trip_id"],
        thresholds=[],
        carve_outs=[
            {
                "condition": "team meals and client entertainment are not covered",
                "reference_kind": None,
            }
        ],
        replaces=[],
    ),
    "TIME-03": dict(
        severity="high",
        scope="receipt",
        triggers=[
            "group := receipts by (employee_id, merchant_name, date), size >= 2; each <= threshold and sum > threshold"
        ],
        required_fields=[
            "employee_id",
            "merchant_name",
            "transaction_datetime",
            "itemized",
            "total_amount_usd",
            "attendee_count",
            "line_items[].amount_usd",
        ],
        thresholds=[
            {
                "value": 75,
                "unit": "USD",
                "basis": "itemization threshold, all receipts non-itemized (DOC-01)",
                "conversion": USD_RATE,
            },
            {
                "value": "employee meal cap",
                "unit": "USD per person",
                "basis": "MEAL-01, REG-02 or REG-03",
                "conversion": USD_RATE,
            },
            {
                "value": 50,
                "unit": "USD",
                "basis": "gift cap for one recipient (GIFT-01)",
                "conversion": USD_RATE,
            },
        ],
        carve_outs=[],
        replaces=["DOC-01", "MEAL-01", "REG-02", "REG-03", "GIFT-01"],
        notes="Out of scoring scope. Emit on every receipt of the group; replaces only the split-around threshold.",
    ),
    "TIME-04": dict(
        severity="review_signal",
        scope="receipt",
        triggers=["weekend date outside trip start/end (needs trip dates)"],
        required_fields=["transaction_datetime", "trip_id"],
        thresholds=[],
        carve_outs=[
            {
                "condition": "requires trip start/end dates; absent in data -> never fires",
                "reference_kind": None,
            }
        ],
        replaces=[],
    ),
}

missing = sorted(set(RULE_DOC) - set(SPEC))
extra = sorted(set(SPEC) - set(RULE_DOC))
print("rules without a spec:", missing or "none", "| specs for unknown rules:", extra or "none")

# %% [markdown]
# ## Assemble and write `rules_draft.yaml`

# %%
ORDER = sorted(RULE_DOC, key=lambda r: (RULE_DOC[r], r))
rules = []
for rid in ORDER:
    s = SPEC[rid]
    rules.append(
        {
            "rule_id": rid,
            "policy_doc": RULE_DOC[rid],
            "severity": s["severity"],
            "scope": s["scope"],
            "triggers": s["triggers"],
            "required_fields": s["required_fields"],
            "thresholds": s["thresholds"],
            "carve_outs": s["carve_outs"],
            "replaces": s["replaces"],
            "literal_text": LITERAL[rid],
            "notes": s.get("notes", ""),
            "status": "DRAFT",
        }
    )
(EXP / "policy" / "rules_draft.yaml").write_text(
    yaml.safe_dump(rules, sort_keys=False, allow_unicode=True, width=100)
)
summary = pd.DataFrame(
    [
        {
            "rule_id": r["rule_id"],
            "doc": r["policy_doc"],
            "severity": str(r["severity"]),
            "scope": r["scope"],
            "replaces": ", ".join(r["replaces"]),
        }
        for r in rules
    ]
)
print(len(rules), "rules written")
summary

# %%
summary.groupby(["scope"]).size().rename("rules"), summary["severity"].value_counts()

# %% [markdown]
# ## Precedence table
#
# Which rule wins when two would fire on the same lines. Read it as "the left rule is reported,
# the right rules are not, under the condition".

# %%
precedence = pd.DataFrame(
    [
        (
            "REG-01",
            "ALC-01, ALC-02, ALC-03",
            "employee entity is APAC (IN, JP, SG)",
            "MCC-01 still applies",
        ),
        ("REG-02", "MEAL-01", "employee entity is APAC", "$60 per person per day"),
        ("REG-03", "MEAL-01", "employee entity is EMEA", "EUR 70 per person per day, converted"),
        (
            "GIFT-04",
            "GIFT-01",
            "lines provided to a government official",
            "meal caps still apply to the receipt",
        ),
        ("GIFT-02", "GIFT-01", "gift cards and cash equivalents", "GIFT-02 alone"),
        (
            "TIME-03",
            "DOC-01, MEAL-01, REG-02, REG-03, GIFT-01",
            "a split group around that threshold",
            "only the threshold split around",
        ),
        ("MCC-03", "ALC-03", "MCC 5813 bars", "bars are on-premises: ALC-01/ALC-02"),
        (
            "EXC-03",
            "every other rule, for that item",
            "item category uncertain",
            "item removed from all other calculations",
        ),
        (
            "ALC-03",
            "ALC-01, ALC-02",
            "merchant is not MCC 5812, 5813 or 7011",
            "scope note under ALC-02",
        ),
    ],
    columns=["reported", "instead of", "when", "note"],
)
precedence

# %%
# Consistency: every "instead of" relation in the table is also in the YAML `replaces` field.
rep = {r["rule_id"]: set(r["replaces"]) for r in rules}
for winner, losers in [
    ("REG-01", {"ALC-01", "ALC-02", "ALC-03"}),
    ("REG-02", {"MEAL-01"}),
    ("REG-03", {"MEAL-01"}),
    ("GIFT-04", {"GIFT-01"}),
    ("GIFT-02", {"GIFT-01"}),
]:
    assert losers <= rep[winner], winner
assert rep["TIME-03"]
print("precedence relations present in rules_draft.yaml")

# %% [markdown]
# ## Policy ambiguities
#
# Places where the text admits more than one reading. Each quote is copied from the policy and
# checked below; each proposed assumption is a DRAFT for Luis to accept or change.

# %%
AMBIGUITIES = [
    {
        "rule_ids": ["REG-03", "REG-04"],
        "quote": "Convert EUR 70 to USD at the euro rate on the transaction date — for a euro receipt, that is the receipt's own rate",
        "why": "For an EMEA employee paying in USD, INR or JPY the record only carries that currency's rate to USD, so the euro rate on that date is not on the expense and has to come from somewhere else.",
        "proposed_assumption": "Use the receipt's own rate for EUR receipts; for other currencies use a fixed EUR-USD table keyed by date, kept in the repo with its source, and route to review if the date is missing from it.",
    },
    {
        "rule_ids": ["REG-04"],
        "quote": "Where the expense record does not capture a VAT number, treat it as missing.",
        "why": "The data never captures a VAT number, so read literally every EMEA receipt above EUR 50 raises REG-04, and it is not stated whether the rule follows the employee's entity or the country where the money was spent.",
        "proposed_assumption": "Apply REG-04 to every receipt of an EMEA-entity employee above EUR 50, because the rule sits under the EMEA entity heading, and accept the many low exceptions it produces.",
    },
    {
        "rule_ids": ["EXC-03"],
        "quote": "Where the category of an item cannot be determined with sufficient confidence, raise a review signal with rule ID EXC-03",
        "why": "The policy names no confidence threshold, model confidence is not calibrated by default, and the evaluation counts every EXC-03 signal as unmatched while the policy says a missed review is cheaper than a false accusation.",
        "proposed_assumption": "Pick the threshold on the synthetic dev set, report how often it fired and what it cost in the evaluation, and argue for a higher threshold in production.",
    },
    {
        "rule_ids": ["HEALTH-01"],
        "quote": "Above $25, or on a receipt with no trip record, it is a low exception, raised on each such receipt and citing its medication lines.",
        "why": "When a trip's OTC total crosses $25 across several receipts, it is unclear whether every receipt with medication on that trip raises the exception or only the receipts from the one that crossed the limit onward.",
        "proposed_assumption": "Raise HEALTH-01 on every trip-linked receipt that has OTC medication lines once the trip total exceeds $25, because each such receipt contributes to the breach.",
    },
    {
        "rule_ids": ["PERS-01", "PERS-02", "EXC-02"],
        "quote": "a baggage-delay reference for the PERS-01 and PERS-02 carve-outs",
        "why": "The single reference field does not say what kind of reference it holds, and the data dictionary says every reference in the dataset is a PA- pre-approval, so the engine has to infer the kind from the format.",
        "proposed_assumption": "Infer the kind from the prefix: PA- is a pre-approval and only satisfies TECH-02; no prefix in the data maps to a baggage-delay, VP or manager approval, so those carve-outs never apply.",
    },
    {
        "rule_ids": ["ENT-01", "TECH-03"],
        "quote": "Golf, sporting events, theatre, concerts, and similar venue spend requires prior VP approval",
        "why": "The taxonomy has no category for event tickets or mobile phones and sends them to other, so the engine cannot detect these rules from the category alone and needs either the MCC or the item text.",
        "proposed_assumption": "Let the classifier return other plus a short subtype (event_ticket, mobile_handset, prescription_medication) and have the engine read only that structured subtype, never free text.",
    },
    {
        "rule_ids": ["GIFT-01"],
        "quote": "An item is a gift when the receipt is declared as Client Gifts or the line names who it is for.",
        "why": "An item in the gift category on a receipt declared as something else with no recipient named is, by this definition, not a gift, so a bouquet on an Office Supplies receipt escapes GIFT-01 entirely.",
        "proposed_assumption": "Follow the definition literally: such an item is not tested under GIFT-01, and DOC-03 catches the mismatch between the declared type and the contents.",
    },
    {
        "rule_ids": ["MEAL-01"],
        "quote": "travel is international when the receipt's currency differs from the currency of the employee's home country, and domestic otherwise.",
        "why": "The data has no home-currency field, so the engine needs a country-to-currency table, and a GLOBAL employee from a country with a currency missing from the data has no defined domestic currency.",
        "proposed_assumption": "Keep a small explicit country-to-currency table for the countries in the data, and treat an unknown home currency as a reason to route the receipt to review rather than guess.",
    },
]
docs_norm = [norm(t) for t in DOCS.values()]
for a in AMBIGUITIES:
    assert any(norm(a["quote"]) in d for d in docs_norm), a["quote"]
    assert len(a["quote"].split()) >= 8 and len(a["why"].split()) >= 15
    assert len(a["proposed_assumption"].split()) >= 10
    assert set(a["rule_ids"]) <= set(RULE_DOC)
for a in AMBIGUITIES:
    a["status"] = "DRAFT"
(EXP / "policy" / "policy_ambiguities.yaml").write_text(
    yaml.safe_dump(AMBIGUITIES, sort_keys=False, allow_unicode=True, width=100)
)
print(len(AMBIGUITIES), "ambiguities written, every quote verbatim")
pd.DataFrame(
    [{"rules": ", ".join(a["rule_ids"]), "quote": a["quote"][:80] + "…"} for a in AMBIGUITIES]
)
