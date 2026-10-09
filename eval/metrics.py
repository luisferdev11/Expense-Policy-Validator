"""Evaluation metrics over comparison rows. Every metric carries its N (constitution VI).

Matching follows data/README.md: an exception matches an answer on (receipt, rule_id); its
evidence is correct when its line IDs equal the answer's (both empty for whole-receipt rules);
review signals match on (receipt, rule_id). Only scored (in-scope) receipts count.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any

from expense_validator.engine.disposition import disposition

DISPOSITIONS = ["flag", "review", "pass"]
Rows = Sequence[dict[str, Any]]
Z95 = 1.959963984540054


def _scored(rows: Rows) -> list[dict[str, Any]]:
    return [r for r in rows if r["scored"]]


def wilson(k: int, n: int) -> tuple[float, float]:
    """Wilson score 95 % interval for k successes out of n."""
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    denom = 1 + Z95**2 / n
    centre = (p + Z95**2 / (2 * n)) / denom
    half = Z95 * math.sqrt(p * (1 - p) / n + Z95**2 / (4 * n * n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def _proportion(k: int, n: int) -> dict[str, Any]:
    lo, hi = wilson(k, n)
    return {
        "value": k,
        "n": n,
        "rate": (k / n) if n else None,
        "interval": [round(lo, 4), round(hi, 4)],
    }


def _f1(tp: int, fp: int, fn: int) -> float:
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    return 2 * precision * recall / (precision + recall) if precision + recall else 0.0


def confusion_matrix(rows: Rows) -> dict[str, Any]:
    """3x3 disposition matrix over scored rows: rows are answers, columns are predictions."""
    scored = _scored(rows)
    matrix = [[0, 0, 0] for _ in DISPOSITIONS]
    for row in scored:
        i = DISPOSITIONS.index(row["answer_disposition"])
        j = DISPOSITIONS.index(row["predicted_disposition"])
        matrix[i][j] += 1
    return {"labels": list(DISPOSITIONS), "matrix": matrix, "n": len(scored)}


def _lines(rows: Rows) -> list[dict[str, Any]]:
    return [line for r in _scored(rows) for line in r["lines"]]


def macro_f1(rows: Rows) -> dict[str, Any]:
    """Mean per-category F1 over the categories present in the answers; a category never
    predicted has precision 0, so F1 0."""
    lines = _lines(rows)
    if lines and all(line["predicted_category"] is None for line in lines):
        return {"value": None, "n": len(lines), "categories": 0, "note": "no categories"}
    categories = sorted({line["answer_category"] for line in lines})
    per_category: dict[str, float] = {}
    for c in categories:
        tp = sum(1 for x in lines if x["predicted_category"] == c and x["answer_category"] == c)
        fp = sum(1 for x in lines if x["predicted_category"] == c and x["answer_category"] != c)
        fn = sum(1 for x in lines if x["predicted_category"] != c and x["answer_category"] == c)
        per_category[c] = _f1(tp, fp, fn)
    value = sum(per_category.values()) / len(categories) if categories else None
    return {
        "value": value,
        "n": len(lines),
        "categories": len(categories),
        "per_category": {c: round(v, 4) for c, v in per_category.items()},
    }


def restricted_f1(rows: Rows) -> dict[str, Any]:
    """F1 on the restricted decision, restricted = true positive; None counts as negative."""
    lines = _lines(rows)
    tp = sum(1 for x in lines if x["predicted_restricted"] is True and x["answer_restricted"])
    fp = sum(1 for x in lines if x["predicted_restricted"] is True and not x["answer_restricted"])
    fn = sum(1 for x in lines if x["predicted_restricted"] is not True and x["answer_restricted"])
    return {"value": _f1(tp, fp, fn), "n": len(lines), "tp": tp, "fp": fp, "fn": fn}


def false_positives(rows: Rows) -> dict[str, Any]:
    """Of the receipts that should pass, how many were flagged or sent to review."""
    should_pass = [r for r in _scored(rows) if r["answer_disposition"] == "pass"]
    k = sum(1 for r in should_pass if r["predicted_disposition"] != "pass")
    return _proportion(k, len(should_pass))


def missed_violations(rows: Rows) -> dict[str, Any]:
    """Of the receipts that should be flagged, how many were passed or downgraded to review."""
    should_flag = [r for r in _scored(rows) if r["answer_disposition"] == "flag"]
    k = sum(1 for r in should_flag if r["predicted_disposition"] != "flag")
    return _proportion(k, len(should_flag))


def disposition_accuracy(rows: Rows) -> dict[str, Any]:
    scored = _scored(rows)
    k = sum(1 for r in scored if r["predicted_disposition"] == r["answer_disposition"])
    return _proportion(k, len(scored))


def per_rule(rows: Rows) -> dict[str, dict[str, Any]]:
    counts: dict[str, dict[str, int]] = {}
    for r in _scored(rows):
        predicted = {e["rule_id"] for e in r.get("predicted_exceptions", [])}
        answer = {e["rule_id"] for e in r.get("answer_exceptions", [])}
        for rule in predicted | answer:
            c = counts.setdefault(rule, {"tp": 0, "fp": 0, "fn": 0})
            if rule in predicted and rule in answer:
                c["tp"] += 1
            elif rule in predicted:
                c["fp"] += 1
            else:
                c["fn"] += 1
    out: dict[str, dict[str, Any]] = {}
    for rule in sorted(counts):
        c = counts[rule]
        out[rule] = {
            **c,
            "precision": c["tp"] / (c["tp"] + c["fp"]) if c["tp"] + c["fp"] else None,
            "recall": c["tp"] / (c["tp"] + c["fn"]) if c["tp"] + c["fn"] else None,
        }
    return out


def evidence_correctness(rows: Rows) -> dict[str, Any]:
    """Among exceptions that match an answer, the share whose line IDs equal the answer's."""
    matched = exact = 0
    for r in _scored(rows):
        answers = {e["rule_id"]: set(e["line_ids"]) for e in r.get("answer_exceptions", [])}
        for e in r.get("predicted_exceptions", []):
            if e["rule_id"] in answers:
                matched += 1
                exact += set(e["line_ids"]) == answers[e["rule_id"]]
    return _proportion(exact, matched)


def signal_match(rows: Rows) -> dict[str, Any]:
    tp = fp = fn = 0
    for r in _scored(rows):
        predicted = {s["rule_id"] for s in r.get("predicted_signals", [])}
        answer = {s["rule_id"] for s in r.get("answer_signals", [])}
        tp, fp, fn = (
            tp + len(predicted & answer),
            fp + len(predicted - answer),
            fn + len(answer - predicted),
        )
    return {"tp": tp, "fp": fp, "fn": fn, "n": tp + fp + fn}


def exc03_effect(rows: Rows) -> dict[str, int]:
    """EXC-03 signals raised (all unmatched by design) and the dispositions they changed."""
    signals = receipts = changed = 0
    for r in _scored(rows):
        own = [s for s in r.get("predicted_signals", []) if s["rule_id"] == "EXC-03"]
        if not own:
            continue
        signals += len(own)
        receipts += 1
        others = [s for s in r.get("predicted_signals", []) if s["rule_id"] != "EXC-03"]
        severities = [e["severity"] for e in r.get("predicted_exceptions", [])]
        if disposition(severities, bool(others)) != r["predicted_disposition"]:
            changed += 1
    return {"signals": signals, "receipts": receipts, "dispositions_changed": changed}


def reg04_vat_only(rows: Rows) -> dict[str, Any]:
    """REG-04 exceptions raised only because the record has no VAT number (A2)."""
    reg04 = [
        e
        for r in _scored(rows)
        for e in r.get("predicted_exceptions", [])
        if e["rule_id"] == "REG-04"
    ]
    k = sum(1 for e in reg04 if (e.get("computed") or {}).get("vat_number") == "not recorded")
    return {"value": k, "n": len(reg04)}


def system_metrics(rows: Rows) -> dict[str, Any]:
    return {
        "macro_f1": macro_f1(rows),
        "restricted_f1": restricted_f1(rows),
        "disposition_confusion": confusion_matrix(rows),
        "disposition_accuracy": disposition_accuracy(rows),
        "false_positives": false_positives(rows),
        "missed_violations": missed_violations(rows),
        "per_rule": per_rule(rows),
        "evidence_correctness": evidence_correctness(rows),
        "review_signals": signal_match(rows),
        "exc03": exc03_effect(rows),
        "reg04_vat_only": reg04_vat_only(rows),
    }
