"""Apply the approved iteration 2 decision rules to the committed results (research R12).

    uv run python -I eval/experiments/decide.py

Reads only committed predictions and caches under explorations/results/iter2/ and the frozen dev
set, never the receipts. Writes outputs/eval/experiments.json deterministically (fixed bootstrap
seed). Each function below implements one registration in experiments_plan.yaml (iteration_2),
word for word; a result that contradicts intuition is reported, never overridden.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from eval.experiments.devset import frozen_hash, load_frozen
from eval.experiments.run_dev import RESULTS
from eval.stats import brier, coverage_accuracy, ece, mcnemar_exact, paired_bootstrap, wilson
from expense_validator.adapters.openrouter.prompt import ParseError, parse
from expense_validator.paths import EVAL_DIR

REFERENCE = "gpt-oss-120b"
MARGIN = -0.02
SCHEMA_LIMIT = 0.02
A6A9_SLACK = 2
REVIEW_BUDGET = 0.10

Rows = Sequence[dict[str, Any]]


def _by_id(rows: Rows) -> dict[str, dict[str, Any]]:
    return {r["item_id"]: r for r in rows}


def _proportion(k: int, n: int) -> dict[str, Any]:
    lo, hi = wilson(k, n)
    return {"value": k / n if n else None, "k": k, "n": n, "interval": [round(lo, 4), round(hi, 4)]}


def _restricted_f1(pred: Rows, items: Sequence[dict[str, Any]]) -> float:
    p = _by_id(pred)
    tp = sum(1 for i in items if p[i["item_id"]]["restricted"] is True and i["restricted"])
    fp = sum(1 for i in items if p[i["item_id"]]["restricted"] is True and not i["restricted"])
    fn = sum(1 for i in items if p[i["item_id"]]["restricted"] is not True and i["restricted"])
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    return 2 * precision * recall / (precision + recall) if precision + recall else 0.0


def _correct(pred: Rows, items: Sequence[dict[str, Any]]) -> list[int]:
    p = _by_id(pred)
    return [int(p[i["item_id"]]["category"] == i["category"]) for i in items]


def _a6a9_wrong(pred: Rows, items: Sequence[dict[str, Any]]) -> int:
    p = _by_id(pred)
    return sum(
        1
        for i in items
        if i.get("a6a9")
        and (
            p[i["item_id"]]["subtype"] != i["subtype"]
            or p[i["item_id"]]["recipient_kind"] != i["recipient_kind"]
        )
    )


def _cost_per_1000(pred: Rows) -> float:
    return 1000 * sum(r.get("cost_usd") or 0.0 for r in pred) / len(pred)


class IncompleteRunError(RuntimeError):
    """A run still has gateway errors: items the model never answered. Re-run to retry them."""


def _complete(results: Mapping[str, Rows]) -> None:
    for name, pred in sorted(results.items()):
        missing = [r["item_id"] for r in pred if r.get("unclassified_reason") == "gateway_error"]
        if missing:
            raise IncompleteRunError(f"{name}: {len(missing)} gateway errors, re-run it first")


def _loss(v: dict[str, Any]) -> str:
    if v["status"] == "excluded":
        sv = v["schema_violations"]
        return f"excluded: {sv['k']}/{sv['n']} schema violations, over 2 %"
    if v["status"] == "fails_a6a9_guard":
        return f"more than 2 extra A6/A9 items wrong ({v['a6a9_wrong']}/{v['a6a9_n']})"
    lo = v["difference"]["interval"][0]
    if lo <= -0.02:
        return f"non-inferiority not shown: bootstrap lower bound {lo} < -0.02"
    return f"restricted F1 {v['restricted_f1']} below the reference's minus 0.01"


def e14(results: Mapping[str, Rows], items: Sequence[dict[str, Any]]) -> dict[str, Any]:
    _complete(results)
    ref = results[REFERENCE]
    ref_correct = _correct(ref, items)
    ref_f1 = _restricted_f1(ref, items)
    ref_a6a9 = _a6a9_wrong(ref, items)
    variants = []
    qualifying = [REFERENCE]
    for name in sorted(results):
        pred = results[name]
        correct = _correct(pred, items)
        violations = sum(
            1
            for r in pred
            if r["status"] != "classified"
            and r.get("unclassified_reason", "schema_violation") == "schema_violation"
        )
        entry: dict[str, Any] = {
            "variant": name,
            "accuracy": _proportion(sum(correct), len(items)),
            "restricted_f1": round(_restricted_f1(pred, items), 4),
            "a6a9_wrong": _a6a9_wrong(pred, items),
            "a6a9_n": sum(1 for i in items if i.get("a6a9")),
            "schema_violations": _proportion(violations, len(items)),
            "cost_per_1000_usd": round(_cost_per_1000(pred), 6),
        }
        if name == REFERENCE:
            entry["status"] = "reference"
            variants.append(entry)
            continue
        b = sum(1 for x, y in zip(correct, ref_correct, strict=True) if x and not y)
        c = sum(1 for x, y in zip(correct, ref_correct, strict=True) if y and not x)
        diff, lo, hi = paired_bootstrap(correct, ref_correct)
        p_value = mcnemar_exact(b, c)
        entry |= {
            "mcnemar": {"b_challenger_only": b, "c_reference_only": c, "p": round(p_value, 4)},
            "difference": {"value": round(diff, 4), "interval": [round(lo, 4), round(hi, 4)]},
        }
        if violations / len(items) > SCHEMA_LIMIT:
            entry["status"] = "excluded"
        elif p_value < 0.05 and b > c and lo > 0:
            entry["status"] = "superior"
        elif (
            lo > MARGIN
            and entry["restricted_f1"] >= ref_f1 - 0.01
            and entry["a6a9_wrong"] <= ref_a6a9 + A6A9_SLACK
        ):
            entry["status"] = "non_inferior"
        elif lo > MARGIN and entry["restricted_f1"] >= ref_f1 - 0.01:
            entry["status"] = "fails_a6a9_guard"
        else:
            entry["status"] = "worse"
        if entry["status"] in {"superior", "non_inferior"}:
            qualifying.append(name)
        variants.append(entry)
    costs = {v["variant"]: v["cost_per_1000_usd"] for v in variants}
    winner = min(qualifying, key=lambda n: (costs[n], n))
    return {
        "id": "E14",
        "factor": "item classifier model",
        "n": len(items),
        "variants": variants,
        "winner": winner,
        "why_others_lost": {
            v["variant"]: _loss(v) if v["variant"] not in qualifying else "more expensive"
            for v in variants
            if v["variant"] != winner
        },
        "note": "Latency was not recorded; ties on cost break by model name.",
    }


def e7(
    winner_rows: Rows, rows_120b: Rows, rows_20b: Rows, items: Sequence[dict[str, Any]]
) -> dict[str, Any]:
    labels = {i["item_id"]: i["category"] for i in items}
    kept = [r for r in winner_rows if r["status"] == "classified"]
    correct = [r["category"] == labels[r["item_id"]] for r in kept]
    self_conf = [float(r["confidence"]) for r in kept]
    a, b = _by_id(rows_120b), _by_id(rows_20b)
    agree = [
        1.0 if a[r["item_id"]]["category"] == b[r["item_id"]]["category"] else 0.0 for r in kept
    ]
    bins_ok = sum(
        1 for k in range(10) if sum(1 for p in self_conf if min(int(p * 10), 9) == k) >= 10
    )
    sources = {
        "self_reported": {
            "brier": round(brier(self_conf, correct), 5),
            "ece": round(ece(self_conf, correct), 5),
            "bins_with_10_items": bins_ok,
            "calibration_measurable": bins_ok >= 3,
        },
        "agreement_120b_20b": {
            "brier": round(brier(agree, correct), 5),
            "ece": round(ece(agree, correct), 5),
        },
    }
    winner = min(sources, key=lambda s: (sources[s]["brier"], s))
    threshold: float | None = None
    curve: list[dict[str, Any]] = []
    if winner == "self_reported":
        total_correct = sum(correct)
        candidates = sorted({0.0, *self_conf})
        best: tuple[float, float] | None = None
        for t in candidates:
            sent = sum(1 for p, c in zip(self_conf, correct, strict=True) if p < t and c)
            kept_items = [c for p, c in zip(self_conf, correct, strict=True) if p >= t]
            if not kept_items or (total_correct and sent / total_correct > REVIEW_BUDGET):
                continue
            accuracy = sum(kept_items) / len(kept_items)
            if best is None or accuracy > best[1]:
                best = (t, accuracy)
        threshold = best[0] if best else 0.0
        curve = coverage_accuracy(self_conf, correct)
    fires = (
        sum(1 for p in self_conf if threshold is not None and p < threshold)
        if winner == "self_reported"
        else sum(1 for x in agree if x == 0.0)
    )
    return {
        "id": "E7",
        "factor": "EXC-03 confidence source and threshold",
        "n": len(kept),
        "sources": sources,
        "winner": winner,
        "threshold": threshold,
        "fires_on_dev": _proportion(fires, len(kept)),
        "curve": [{k: round(v, 4) for k, v in p.items()} for p in curve],
    }


def e5(original: Rows, translate: Rows, items: Sequence[dict[str, Any]]) -> dict[str, Any]:
    subset = [i for i in items if i["language"] != "en"]
    _complete({"original": original, "translate": translate})
    ids = {i["item_id"] for i in subset}
    failed = [
        r["item_id"]
        for r in translate
        if r["item_id"] in ids and "translation" in r and r["translation"] is None
    ]
    if failed:
        raise IncompleteRunError(f"translate: {len(failed)} translation failures, re-run it first")
    orig = _correct(original, subset)
    trans = _correct(translate, subset)
    b = sum(1 for x, y in zip(trans, orig, strict=True) if x and not y)
    c = sum(1 for x, y in zip(trans, orig, strict=True) if y and not x)
    diff, lo, hi = paired_bootstrap(trans, orig)
    p_value = mcnemar_exact(b, c)
    wins = p_value < 0.05 and b > c and lo > 0
    return {
        "id": "E5",
        "factor": "translation before classification",
        "n": len(subset),
        "variants": [
            {"variant": "original", "accuracy": _proportion(sum(orig), len(subset))},
            {"variant": "translate", "accuracy": _proportion(sum(trans), len(subset))},
        ],
        "mcnemar": {"b_translate_only": b, "c_original_only": c, "p": round(p_value, 4)},
        "difference": {"value": round(diff, 4), "interval": [round(lo, 4), round(hi, 4)]},
        "winner": "translate" if wins else "original",
        "why_others_lost": (
            {"original": "translation gains, with McNemar and bootstrap evidence"}
            if wins
            else {"translate": "no evidence of a gain at this N"}
        ),
    }


def _null_subtype(content: str | None) -> bool:
    try:
        obj = json.loads(content or "")
    except json.JSONDecodeError:
        return False
    return isinstance(obj, dict) and "subtype" in obj and obj["subtype"] is None


def e15(results: Mapping[str, Rows], items: Sequence[dict[str, Any]]) -> dict[str, Any]:
    labels = {i["item_id"]: i for i in items}
    observed = fixed = broken = 0
    for rows in results.values():
        for r in rows:
            label = labels[r["item_id"]]
            strict_ok = tolerant_ok = False
            try:
                s = parse(r["raw_content"])
                strict_ok = s.category == label["category"]
            except ParseError:
                pass
            try:
                t = parse(r["raw_content"], null_subtype_as_none=True)
                tolerant_ok = t.category == label["category"]
            except ParseError:
                pass
            observed += int(_null_subtype(r["raw_content"]))
            fixed += int(tolerant_ok and not strict_ok)
            broken += int(strict_ok and not tolerant_ok)
    adopt = observed > 0 and fixed >= 1 and broken == 0
    return {
        "id": "E15",
        "factor": 'reading "subtype": null as "none"',
        "n": sum(len(r) for r in results.values()),
        "observed": observed,
        "fixed": fixed,
        "broken": broken,
        "winner": "null_as_none" if adopt else "strict",
        "why_others_lost": (
            {"strict": "null_as_none fixes answers and breaks none"}
            if adopt
            else {"null_as_none": "not observed on dev" if observed == 0 else "no net fix"}
        ),
    }


def ret(check: dict[str, Any]) -> dict[str, Any]:
    same = check["differences"] == 0
    return {
        "id": "RET",
        "factor": "policy retriever",
        "n": check["cases"],
        "differences": check["differences"],
        "winner": "trigger_map" if same else "investigate",
    }


def _load(path: Path) -> list[dict[str, Any]]:
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x]


def _frac(p: dict[str, Any]) -> str:
    lo, hi = p["interval"]
    return f"{p['k']}/{p['n']} (95 % CI {lo:.3f}-{hi:.3f})"


def _evidence(o: dict[str, Any]) -> str:
    if o["id"] == "E14":
        (w,) = [v for v in o["variants"] if v["variant"] == o["winner"]]
        return f"accuracy {_frac(w['accuracy'])}, restricted F1 {w['restricted_f1']}"
    if o["id"] == "E7":
        brier = o["sources"][o["winner"]]["brier"]
        return f"threshold {o['threshold']}, Brier {brier}, fires on {_frac(o['fires_on_dev'])}"
    if o["id"] == "E5":
        orig, trans = (v["accuracy"] for v in o["variants"])
        return f"original {_frac(orig)}, translate {_frac(trans)}, McNemar p {o['mcnemar']['p']}"
    if o["id"] == "E15":
        return f"{o['observed']} null subtypes in {o['n']} answers, {o['fixed']} fixed"
    return f"{o['differences']} differences on {o['n']} receipts"


def _why(o: dict[str, Any]) -> dict[str, str]:
    if o["id"] == "E7":
        return {
            name: f"higher Brier ({s['brier']})"
            for name, s in o["sources"].items()
            if name != o["winner"]
        }
    if o["id"] == "RET":
        return {"all_rules": "same findings, harder to explain"} if o["differences"] == 0 else {}
    return dict(o.get("why_others_lost") or {})


def table(outcomes: Sequence[dict[str, Any]]) -> list[dict[str, str]]:
    """One row per experiment, for the report and the viewer."""
    return [
        {
            "experiment": o["id"],
            "factor": o["factor"],
            "winner": str(o["winner"]),
            "evidence": _evidence(o),
            "why_others_lost": "; ".join(f"{k}: {v}" for k, v in sorted(_why(o).items())),
        }
        for o in outcomes
    ]


def main() -> int:
    items = load_frozen()
    e14_rows = {p.stem: _load(p) for p in sorted((RESULTS / "E14").glob("*.jsonl"))}
    outcome_e14 = e14(e14_rows, items)
    winner = outcome_e14["winner"]
    outcomes = [
        outcome_e14,
        e7(e14_rows[winner], e14_rows[REFERENCE], e14_rows["gpt-oss-20b"], items),
        e5(e14_rows[REFERENCE], _load(RESULTS / "E5" / "translate.jsonl"), items),
        e15(e14_rows, items),
        ret(json.loads((RESULTS / "RET" / "check.json").read_text(encoding="utf-8"))),
    ]
    kept = [*e14_rows.values(), _load(RESULTS / "E5" / "translate.jsonl")]
    spend = sum(r.get("cost_usd") or 0.0 for rows in kept for r in rows)
    doc = {
        "dev_set_sha256": frozen_hash(),
        "experiments": outcomes,
        "table": table(outcomes),
        "spend_usd_of_kept_answers": round(spend, 6),
    }
    EVAL_DIR.mkdir(parents=True, exist_ok=True)
    (EVAL_DIR / "experiments.json").write_text(
        json.dumps(doc, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    for o in outcomes:
        print(f"{o['id']}: winner {o['winner']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
