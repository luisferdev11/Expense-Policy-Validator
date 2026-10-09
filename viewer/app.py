"""Streamlit viewer v1: receipt list (thin path). Detail and metrics views come in Phase 7.

Reads committed outputs only, through `expense_validator.results`; correct answers come from
the evaluation's comparison output, never from the receipts file. No model call.
"""

from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from expense_validator.results import load_comparison, load_results

st.set_page_config(page_title="Expense Policy Validator", layout="wide")
st.title("Expense Policy Validator")

results = load_results()
comparison: dict[str, dict[str, Any]] = {row["receipt_id"]: row for row in load_comparison()}

if not results:
    st.info("No results yet. Run `uv run epv run`, then `uv run epv eval`.")
    st.stop()

rows = []
for result in results:
    row = comparison.get(result.receipt_id, {})
    answer = row.get("answer_disposition")
    rows.append(
        {
            "receipt": result.receipt_id,
            "predicted": result.disposition,
            "answer": answer or "—",
            "match": "—" if answer is None else ("yes" if answer == result.disposition else "NO"),
            "scored": row.get("scored", False),
            "exceptions": ", ".join(e.rule_id for e in result.exceptions),
            "signals": ", ".join(s.rule_id for s in result.review_signals),
        }
    )
table = pd.DataFrame(rows)


def _highlight(row: pd.Series) -> list[str]:
    style = "background-color: #f8d7da" if row["match"] == "NO" else ""
    return [style] * len(row)


st.subheader("Receipt list")
st.caption(
    f"{len(table)} receipts, {int(table['scored'].sum())} scored. "
    "Mismatches with the correct disposition are highlighted."
)
st.dataframe(table.style.apply(_highlight, axis=1), hide_index=True, use_container_width=True)
