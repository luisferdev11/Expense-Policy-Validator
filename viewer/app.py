"""Streamlit viewer v1: receipt list, receipt detail and metrics (brief Part 5, FR-034).

Reads committed outputs only, through `expense_validator.adapters.results_files`; the
correct answers come from
the evaluation's comparison output, never from the receipts file. No model call, no key.
Launch with `uv run epv view`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

from expense_validator.adapters.results_files import (
    load_comparison,
    load_experiments,
    load_metrics,
    load_results,
)
from expense_validator.adapters.tracing import make_tracer
from expense_validator.app.cli import load_env
from expense_validator.app.intake import default_classifier, parse_upload, run_upload
from expense_validator.paths import EVAL_DIR

st.set_page_config(page_title="Expense Policy Validator", layout="wide")
st.title("Expense Policy Validator")

results = load_results()
comparison: dict[str, dict[str, Any]] = {row["receipt_id"]: row for row in load_comparison()}
metrics = load_metrics()

if not results:
    st.info("No results yet. Run `uv run epv run`, then `uv run epv eval`.")
    st.stop()

view = st.sidebar.radio(
    "View", ["Receipt list", "Receipt detail", "Metrics", "Experiments", "Upload"]
)
run = results[0].run
st.sidebar.caption(
    f"Model `{run.model_id}` · prompt `{run.prompt_version}` · rules `{run.rules_version}` · "
    f"EXC-03 threshold {run.exc03_threshold} ({run.exc03_threshold_status})"
)


def _highlight(row: pd.Series) -> list[str]:
    style = "background-color: #f8d7da" if row["match"] == "NO" else ""
    return [style] * len(row)


if view == "Receipt list":
    rows = []
    for result in results:
        row = comparison.get(result.receipt_id, {})
        answer = row.get("answer_disposition")
        rows.append(
            {
                "receipt": result.receipt_id,
                "predicted": result.disposition,
                "answer": answer or "—",
                "match": "—"
                if answer is None
                else ("yes" if answer == result.disposition else "NO"),
                "scored": row.get("scored", False),
                "exceptions": ", ".join(e.rule_id for e in result.exceptions),
                "signals": ", ".join(s.rule_id for s in result.review_signals),
            }
        )
    table = pd.DataFrame(rows)
    st.subheader("Receipt list")
    st.caption(
        f"{len(table)} receipts, {int(table['scored'].sum())} scored. "
        "Mismatches with the correct disposition are highlighted."
    )
    st.dataframe(table.style.apply(_highlight, axis=1), hide_index=True, use_container_width=True)

elif view == "Receipt detail":
    ids = [r.receipt_id for r in results]
    chosen = st.selectbox("Receipt", ids)
    result = next(r for r in results if r.receipt_id == chosen)
    row = comparison.get(chosen, {})
    st.subheader(chosen)
    left, right = st.columns(2)
    left.markdown(f"**Predicted disposition:** `{result.disposition}`")
    right.markdown(
        f"**Correct disposition:** `{row.get('answer_disposition', '—')}`"
        + ("" if row.get("scored", True) else " (not scored)")
    )

    answers = {line["line_id"]: line for line in row.get("lines", [])}
    st.markdown("#### Line items")
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "line": line.line_id,
                    "description": line.description_raw,
                    "category": line.category or f"unclassified ({line.unclassified_reason})",
                    "confidence": line.confidence,
                    "restricted": line.restricted,
                    "subtype": line.subtype,
                    "recipient": line.recipient_name or "",
                    "correct category": answers.get(line.line_id, {}).get("answer_category", ""),
                }
                for line in result.line_items
            ]
        ),
        hide_index=True,
        use_container_width=True,
    )

    st.markdown("#### Exceptions raised")
    if not result.exceptions:
        st.markdown("None.")
    for exc in result.exceptions:
        st.markdown(
            f"**{exc.rule_id}** · {exc.severity} · `{exc.policy_doc}` · lines: "
            f"{', '.join(exc.line_ids) or 'whole receipt'}"
        )
        st.markdown(f"{exc.explanation}")
        st.markdown(f"> {exc.evidence}")
        if exc.computed:
            st.caption("; ".join(f"{k} = {v}" for k, v in exc.computed.items()))
    st.markdown("#### Review signals")
    if not result.review_signals:
        st.markdown("None.")
    for signal in result.review_signals:
        st.markdown(f"**{signal.rule_id}** · {signal.reason}")

    st.markdown("#### Correct answer")
    for exc in row.get("answer_exceptions", []):
        st.markdown(
            f"**{exc['rule_id']}** · {exc.get('severity', '')} · lines: "
            f"{', '.join(exc.get('line_ids', [])) or 'whole receipt'} · {exc.get('reason', '')}"
        )
    for signal in row.get("answer_signals", []):
        st.markdown(f"**{signal['rule_id']}** (signal) · {signal.get('reason', '')}")
    if row.get("answer_notes"):
        st.caption(row["answer_notes"])

elif view == "Experiments":
    st.subheader("Experiments, decided on the synthetic dev set")
    experiments = load_experiments()
    if not experiments:
        st.info("No experiments yet. Run `uv run python -I eval/experiments/decide.py`.")
        st.stop()
    st.caption(
        f"Frozen dev set `{experiments['dev_set_sha256'][:12]}` · rules registered and approved "
        "before any run (ADR 0005). None of the 28 scored receipts informed a choice."
    )
    st.dataframe(pd.DataFrame(experiments["table"]), hide_index=True, width="stretch")

elif view == "Upload":
    st.subheader("Validate new receipts")
    st.caption(
        "One receipt (JSON object), a JSON array, or JSONL. Answer keys are stripped as for the "
        "dataset, and the uploaded batch is the context for cross-receipt rules (meal days, "
        "trips). Lines seen before cost nothing; new lines call the classifier and are traced."
    )
    upload = st.file_uploader("Receipt file", type=["json", "jsonl"])
    pasted = st.text_area("Or paste JSON", height=160)
    source = upload.getvalue().decode("utf-8") if upload is not None else pasted
    if st.button("Validate", type="primary", disabled=not source.strip()):
        parsed = parse_upload(source)
        for bad_row, message in parsed.errors:
            st.error(f"Row {bad_row}: {message}")
        if parsed.receipts:
            load_env()
            tracer = make_tracer()
            classifier = default_classifier(tracer)
            with st.spinner(f"Validating {len(parsed.receipts)} receipts"):
                upload_run = run_upload(parsed.receipts, classifier, tracer)
            tracer.flush(timeout_s=10.0)
            st.session_state["upload_run"] = {
                "run_id": upload_run.run_id,
                "path": str(upload_run.path),
                "calls": getattr(classifier, "calls_made", 0),
                "usd": getattr(classifier, "run_spend_usd", 0.0),
                "errors": len(parsed.errors),
            }
    last = st.session_state.get("upload_run")
    if last:
        uploaded = load_results(Path(last["path"]))
        st.success(
            f"Run {last['run_id']}: {len(uploaded)} receipts validated, {last['errors']} rows "
            f"rejected, {last['calls']} new model calls (USD {last['usd']:.6f})."
        )
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "receipt": r.receipt_id,
                        "disposition": r.disposition,
                        "exceptions": ", ".join(
                            f"{e.rule_id} ({e.severity})" for e in r.exceptions
                        ),
                        "signals": ", ".join(s.rule_id for s in r.review_signals),
                    }
                    for r in uploaded
                ]
            ),
            hide_index=True,
            width="stretch",
        )
        for r in uploaded:
            with st.expander(f"{r.receipt_id} · {r.disposition}"):
                for li in r.line_items:
                    st.markdown(
                        f"`{li.line_id}` {li.description_raw} · **{li.category or 'unclassified'}**"
                        f" · confidence {li.confidence if li.confidence is not None else '—'}"
                    )
                for e in r.exceptions:
                    st.markdown(
                        f"**{e.rule_id}** ({e.severity}) · lines {', '.join(e.line_ids) or '—'}"
                    )
                    st.markdown(e.explanation)
                    st.caption(f"{e.policy_doc}: “{e.evidence}”")
                for s in r.review_signals:
                    st.markdown(f"**{s.rule_id}** (signal) · {s.reason}")

else:
    st.subheader("Metrics")
    systems = metrics.get("systems", {})
    if not systems:
        st.info("No metrics yet. Run `uv run epv eval`.")
        st.stop()
    pipeline = systems["pipeline"]
    a, b, c, d = st.columns(4)
    a.metric("Macro F1", f"{pipeline['macro_f1']['value']:.3f}", f"N = {pipeline['macro_f1']['n']}")
    b.metric(
        "Restricted F1",
        f"{pipeline['restricted_f1']['value']:.3f}",
        f"N = {pipeline['restricted_f1']['n']}",
    )
    fp, missed = pipeline["false_positives"], pipeline["missed_violations"]
    c.metric("False positives", f"{fp['value']} of {fp['n']}")
    d.metric("Missed violations", f"{missed['value']} of {missed['n']}")
    report = EVAL_DIR / "report.md"
    if report.exists():
        st.markdown(report.read_text(encoding="utf-8"))
