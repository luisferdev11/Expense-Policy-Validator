"""Streamlit viewer v1: receipt list, receipt detail and metrics (brief Part 5, FR-034).

Reads committed outputs only, through `expense_validator.adapters.results_files`; the
correct answers come from
the evaluation's comparison output, never from the receipts file. No model call, no key.
Launch with `uv run epv view`.
"""

from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from expense_validator.adapters.results_files import load_comparison, load_metrics, load_results
from expense_validator.paths import EVAL_DIR

st.set_page_config(page_title="Expense Policy Validator", layout="wide")
st.title("Expense Policy Validator")

results = load_results()
comparison: dict[str, dict[str, Any]] = {row["receipt_id"]: row for row in load_comparison()}
metrics = load_metrics()

if not results:
    st.info("No results yet. Run `uv run epv run`, then `uv run epv eval`.")
    st.stop()

view = st.sidebar.radio("View", ["Receipt list", "Receipt detail", "Metrics"])
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
