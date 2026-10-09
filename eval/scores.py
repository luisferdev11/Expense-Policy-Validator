"""Attach evaluation results to the pipeline's traces as Langfuse scores (contracts/tracing.md).

Scores go on the trace IDs of the run that produced the results (its label is in the gitignored
.cache/last_run.json). Only when Langfuse is reachable; otherwise a warning and nothing else.
Answers reach Langfuse only here, as scores, never inside a pipeline trace (FR-027).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from expense_validator.tracing import LangfuseTracer, make_tracer, trace_id_for


def post_scores(
    rows: Sequence[dict[str, Any]], run_label: str, env: Mapping[str, str] | None = None
) -> int:
    tracer = make_tracer(env=env)
    inner = tracer.inner
    if not isinstance(inner, LangfuseTracer):
        return 0
    client = inner.client
    posted = 0
    for row in rows:
        if not row["scored"]:
            continue
        trace_id = trace_id_for(run_label, row["receipt_id"])
        answers = {e["rule_id"] for e in row["answer_exceptions"]}
        predicted = {e["rule_id"] for e in row["predicted_exceptions"]}
        lines = row["lines"]
        values: dict[str, float] = {
            "disposition_correct": float(row["predicted_disposition"] == row["answer_disposition"]),
            "category_correct_rate": (
                sum(x["predicted_category"] == x["answer_category"] for x in lines) / len(lines)
                if lines
                else 1.0
            ),
            "exceptions_matched": float(len(predicted & answers)),
            "exceptions_extra": float(len(predicted - answers)),
        }
        for name, value in values.items():
            client.create_score(name=name, value=value, trace_id=trace_id, data_type="NUMERIC")
            posted += 1
    tracer.flush(timeout_s=10.0)
    return posted
