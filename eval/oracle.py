"""The oracle ablation (research R10): the engine fed the answer categories.

Inside eval/ only, because it reads answers. The OracleClassifier returns each line's answer
category and restricted flag with confidence 1.0. The answers do not label subtype or recipient,
so both are `none`: rules that need them (ENT-01, TECH-03, HEALTH-01 prescription, GIFT-01,
GIFT-03, GIFT-04) are under-tested by the oracle, and the report says so. The same pipeline
code runs the 28 in-scope receipts; comparing its dispositions with the pipeline's attributes
each error to a stage.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from eval.answers import Answer, load_answers
from eval.compare import compare
from eval.metrics import _proportion
from expense_validator.adapters.config_files import load_settings
from expense_validator.adapters.receipts_file import load_receipts
from expense_validator.adapters.tracing import NoopTracer
from expense_validator.app.pipeline import run_pipeline
from expense_validator.domain.models import Classification, ClassificationSource, ClassifierRequest

Rows = Sequence[dict[str, Any]]

LIMITATION = (
    "The answers label category and restricted flag only. The oracle sets subtype and recipient "
    "to none, so ENT-01, TECH-03, the HEALTH-01 prescription carve-out and GIFT-01/03/04 cannot "
    "fire on the oracle side."
)
STAGES = {
    (False, True): "classification",
    (False, False): "rule_logic_or_convention",
    (True, False): "right_for_wrong_reason",
    (True, True): "none",
}
# Rules whose outcome depends on subtype or recipient, which the oracle cannot supply.
LIMITED_RULES = frozenset({"ENT-01", "TECH-03", "HEALTH-01", "GIFT-01", "GIFT-03", "GIFT-04"})


def _rule_ids(row: dict[str, Any]) -> set[str]:
    return {e["rule_id"] for e in row.get("predicted_exceptions", [])}


def _stage(p: dict[str, Any], o: dict[str, Any]) -> str:
    stage = STAGES[(_ok(p), _ok(o))]
    if stage == "right_for_wrong_reason" and (_rule_ids(p) ^ _rule_ids(o)) & LIMITED_RULES:
        return "oracle_limitation"
    return stage


SOURCE = ClassificationSource(
    classifier="oracle",
    model_id="answers",
    provider_endpoint="none",
    prompt_version="oracle",
    cache_key="oracle",
    request_id=None,
    cost_usd=None,
    prompt_tokens=None,
    completion_tokens=None,
    cache_hit=True,
)


class OracleClassifier:
    name = "oracle"
    model_id = "answers"
    provider_endpoint = "none"
    prompt_version = "oracle"

    def __init__(self, answers: dict[str, Answer]) -> None:
        self._lines = {lid: line for a in answers.values() for lid, line in a.lines.items()}

    def classify(self, line_id: str, request: ClassifierRequest) -> Classification:
        line = self._lines[line_id]
        return Classification(
            line_id=line_id,
            status="classified",
            category=line["category"],
            restricted=line["restricted"],
            confidence=1.0,
            subtype="none",
            recipient_kind="none",
            recipient_name=None,
            unclassified_reason=None,
            source=SOURCE,
        )


def _ok(row: dict[str, Any]) -> bool:
    return bool(row["predicted_disposition"] == row["answer_disposition"])


def attribute(pipeline: Rows, oracle: Rows) -> dict[str, Any]:
    """Per scored receipt: whether each side got the disposition right, and the stage to blame."""
    by_id = {r["receipt_id"]: r for r in oracle}
    rows = []
    for p in pipeline:
        if not p["scored"]:
            continue
        o = by_id[p["receipt_id"]]
        rows.append(
            {
                "receipt_id": p["receipt_id"],
                "answer_disposition": p["answer_disposition"],
                "pipeline_disposition": p["predicted_disposition"],
                "oracle_disposition": o["predicted_disposition"],
                "stage": _stage(p, o),
            }
        )
    n = len(rows)
    return {
        "pipeline_accuracy": _proportion(
            sum(r["pipeline_disposition"] == r["answer_disposition"] for r in rows), n
        ),
        "oracle_accuracy": _proportion(
            sum(r["oracle_disposition"] == r["answer_disposition"] for r in rows), n
        ),
        "rows": rows,
        "limitation": LIMITATION,
    }


def oracle_rows() -> list[dict[str, Any]]:
    """Run the pipeline over every receipt with the oracle classifier, compared with answers."""
    answers = load_answers()
    results = run_pipeline(
        load_receipts(), OracleClassifier(answers), NoopTracer(), load_settings(), "oracle"
    )
    return compare(results, answers)
