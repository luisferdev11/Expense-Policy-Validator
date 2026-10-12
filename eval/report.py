"""`epv eval`: comparison.jsonl, metrics.json and report.md from committed outputs only.

No model call, no key. Re-running reproduces the files byte for byte (FR-029). Three systems are
scored on the 28 in-scope receipts: the pipeline, keyword-classifier and keyword-flagger.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from eval.answers import load_answers
from eval.base_rate import base_rate_table
from eval.baselines import run_flagger
from eval.compare import compare
from eval.failure_cases import FAILURE_CASES, render_failure_cases
from eval.metrics import system_metrics
from eval.oracle import attribute, oracle_rows
from eval.scope import OUT_OF_SCOPE
from expense_validator.adapters.results_files import load_experiments, load_results
from expense_validator.paths import BASELINES_DIR

KEYWORD_CLASSIFIER = BASELINES_DIR / "keyword_classifier" / "results.jsonl"
KEYWORD_FLAGGER = BASELINES_DIR / "keyword_flagger" / "results.jsonl"


def _pct(x: float | None) -> str:
    return "n/a" if x is None else f"{100 * x:.1f} %"


def _num(x: float | None, digits: int = 3) -> str:
    return "n/a" if x is None else f"{x:.{digits}f}"


def _prop(m: dict[str, Any]) -> str:
    lo, hi = m["interval"]
    return f"{m['value']} of {m['n']} ({_pct(m['rate'])}; 95 % CI {_pct(lo)} to {_pct(hi)})"


def _summary(systems: dict[str, dict[str, Any]]) -> list[str]:
    names = list(systems)
    out = [
        "| Measure | " + " | ".join(names) + " |",
        "|---|" + "---|" * len(names),
    ]

    def row(label: str, render: Any) -> None:
        out.append(f"| {label} | " + " | ".join(render(systems[n]) for n in names) + " |")

    row(
        "Macro F1 (categories)",
        lambda m: f"{_num(m['macro_f1']['value'])} (N = {m['macro_f1']['n']})",
    )
    row(
        "Restricted F1",
        lambda m: f"{_num(m['restricted_f1']['value'])} (N = {m['restricted_f1']['n']})",
    )
    row("Disposition accuracy", lambda m: _prop(m["disposition_accuracy"]))
    row("False positives (should pass)", lambda m: _prop(m["false_positives"]))
    row("Missed violations (should flag)", lambda m: _prop(m["missed_violations"]))
    return out


def _better(systems: dict[str, dict[str, Any]]) -> list[str]:
    """Where a baseline does better than the pipeline, stated mechanically."""
    p = systems["pipeline"]
    lines = []
    for name, m in systems.items():
        if name == "pipeline":
            continue
        checks = [
            ("macro F1", m["macro_f1"]["value"], p["macro_f1"]["value"], True),
            ("restricted F1", m["restricted_f1"]["value"], p["restricted_f1"]["value"], True),
            (
                "false positives",
                m["false_positives"]["value"],
                p["false_positives"]["value"],
                False,
            ),
            (
                "missed violations",
                m["missed_violations"]["value"],
                p["missed_violations"]["value"],
                False,
            ),
        ]
        wins = [
            label
            for label, theirs, ours, higher in checks
            if theirs is not None
            and ours is not None
            and (theirs > ours if higher else theirs < ours)
        ]
        lines.append(
            f"- **{name}** does better on: {', '.join(wins) if wins else 'nothing measured here'}."
        )
    return lines


def _matrix(cm: dict[str, Any]) -> list[str]:
    out = [
        f"N = {cm['n']} (rows: answer, columns: prediction)",
        "",
        "| answer \\ predicted | " + " | ".join(cm["labels"]) + " |",
        "|---|" + "---|" * len(cm["labels"]),
    ]
    for label, values in zip(cm["labels"], cm["matrix"], strict=True):
        out.append(f"| {label} | " + " | ".join(str(v) for v in values) + " |")
    return out


def _experiments(rows: list[dict[str, str]]) -> list[str]:
    lines = [
        "## Experiments, decided on the synthetic dev set",
        "",
        "Each rule was registered and approved before its run; the 28 scored receipts informed "
        "no choice (ADR 0005, `outputs/eval/experiments.json`).",
        "",
        "| Experiment | Factor | Winner | Evidence | Why the others lost |",
        "|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(
            f"| {r['experiment']} | {r['factor']} | {r['winner']} | {r['evidence']} | "
            f"{r['why_others_lost'] or '-'} |"
        )
    return [*lines, ""]


def _oracle(o: dict[str, Any]) -> list[str]:
    wrong = [r for r in o["rows"] if r["stage"] != "none"]
    lines = [
        "## Oracle ablation: where errors come from",
        "",
        "The same pipeline code, fed each line's answer category with confidence 1.0 "
        "(research R10).",
        "",
        f"- **Pipeline disposition accuracy:** {_prop(o['pipeline_accuracy'])}.",
        f"- **Oracle disposition accuracy:** {_prop(o['oracle_accuracy'])}.",
        f"- **Limitation:** {o['limitation']}",
        "- **Stages:** `classification` (only the oracle is right), `rule_logic_or_convention` "
        "(both wrong), `right_for_wrong_reason` (only the pipeline is right), "
        "`oracle_limitation` (only the pipeline is right, through a rule that needs subtype or "
        "recipient).",
        "",
    ]
    if not wrong:
        return [*lines, "Both sides get every scored disposition right.", ""]
    lines += [
        "| Receipt | Answer | Pipeline | Oracle | Stage |",
        "|---|---|---|---|---|",
    ]
    for r in wrong:
        lines.append(
            f"| {r['receipt_id']} | {r['answer_disposition']} | {r['pipeline_disposition']} | "
            f"{r['oracle_disposition']} | {r['stage']} |"
        )
    return [*lines, ""]


def _render(metrics: dict[str, Any]) -> str:
    systems = metrics["systems"]
    p = systems["pipeline"]
    run = metrics["run"]
    lines = [
        "# Evaluation report",
        "",
        "Generated by `uv run epv eval` from committed outputs; no model call. Scored on the "
        f"{p['disposition_confusion']['n']} in-scope receipts; not scored: "
        f"{', '.join(sorted(OUT_OF_SCOPE))}.",
        "",
        f"Pipeline run: classifier `{run.get('classifier')}`, model `{run.get('model_id')}` "
        f"({run.get('provider_endpoint')}), prompt `{run.get('prompt_version')}`, rules "
        f"`{run.get('rules_version')}`, EXC-03 threshold {run.get('exc03_threshold')} "
        f"({run.get('exc03_threshold_status')}).",
        "",
        "## Summary",
        "",
        *_summary(systems),
        "",
        "### Where a baseline does better",
        "",
        *_better(systems),
        "",
        "## Disposition confusion matrices",
        "",
    ]
    for name, m in systems.items():
        lines += [f"### {name}", "", *_matrix(m["disposition_confusion"]), ""]
    ev, sig, exc03, reg04 = (
        p["evidence_correctness"],
        p["review_signals"],
        p["exc03"],
        p["reg04_vat_only"],
    )
    lines += [
        "## Pipeline: rules, evidence and signals",
        "",
        "Exceptions match an answer on (receipt, rule_id) (data/README.md).",
        "",
        "| Rule | TP | FP | FN | Precision | Recall |",
        "|---|---|---|---|---|---|",
    ]
    for rule, c in p["per_rule"].items():
        lines.append(
            f"| {rule} | {c['tp']} | {c['fp']} | {c['fn']} | {_num(c['precision'], 2)} | "
            f"{_num(c['recall'], 2)} |"
        )
    lines += [
        "",
        f"- **Evidence correctness** (matched exceptions whose line IDs equal the answer's): "
        f"{_prop(ev)}.",
        f"- **Review signals** matched on (receipt, rule_id): {sig['tp']} matched, {sig['fp']} "
        f"extra, {sig['fn']} missed.",
        f"- **EXC-03** (no answer uses it, so each one counts as unmatched): {exc03['signals']} "
        f"signals on {exc03['receipts']} receipts; dispositions changed: "
        f"{exc03['dispositions_changed']}.",
        f"- **REG-04 from the absent VAT field only** (decision A2): {reg04['value']} of "
        f"{reg04['n']} REG-04 exceptions.",
        "",
        *(_oracle(metrics["oracle"]) if "oracle" in metrics else []),
        *(_experiments(metrics["experiments"]) if metrics.get("experiments") else []),
        "## Base rate",
        "",
    ]
    br = metrics["base_rate"]
    lines += [
        f"Measured on this dataset: false-positive rate {_pct(br['false_positive_rate'])} "
        f"(N = {br['n_pass']} should-pass receipts) and detection rate "
        f"{_pct(br['detection_rate'])} (N = {br['n_flag']} should-flag receipts). Per "
        f"{br['receipts']:,} receipts:",
        "",
        "| Prevalence | Violations | True flags | False flags | Share of flags that are false |",
        "|---|---|---|---|---|",
    ]
    for r in br["rows"]:
        lines.append(
            f"| {_pct(r['prevalence'])} | {r['violations']:.0f} | {r['true_flags']:.0f} | "
            f"{r['false_flags']:.0f} | {_pct(r['false_share'])} |"
        )
    lines += [
        "",
        "With N = 9 should-pass receipts the false-positive rate is very uncertain (see its "
        "interval above); a production estimate needs a larger, realistic sample.",
        "",
        "## Failure cases",
        "",
        *render_failure_cases(FAILURE_CASES),
    ]
    return "\n".join(lines)


def run_eval(
    results_path: Path, out_dir: Path, baselines: dict[str, Path] | None = None
) -> dict[str, Any]:
    answers = load_answers()
    if baselines is None:
        run_flagger(KEYWORD_FLAGGER)
        baselines = {"keyword-classifier": KEYWORD_CLASSIFIER, "keyword-flagger": KEYWORD_FLAGGER}
    results = load_results(results_path)
    rows = {"pipeline": compare(results, answers)}
    for name, path in baselines.items():
        if path.exists():
            rows[name] = compare(load_results(path), answers)
    systems = {name: system_metrics(r) for name, r in rows.items()}
    p = systems["pipeline"]
    metrics: dict[str, Any] = {
        "run": results[0].run.model_dump(mode="json") if results else {},
        "systems": systems,
        "oracle": attribute(rows["pipeline"], oracle_rows()),
        "experiments": load_experiments().get("table", []),
        "base_rate": base_rate_table(
            fp=p["false_positives"]["value"],
            n_pass=p["false_positives"]["n"],
            missed=p["missed_violations"]["value"],
            n_flag=p["missed_violations"]["n"],
        ),
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "comparison.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows["pipeline"]),
        encoding="utf-8",
    )
    (out_dir / "metrics.json").write_text(
        json.dumps(metrics, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (out_dir / "report.md").write_text(_render(metrics) + "\n", encoding="utf-8")
    metrics["rows"] = rows["pipeline"]
    return metrics
