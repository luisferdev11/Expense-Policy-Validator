"""The oracle ablation (research R10), on synthetic rows and answers only."""

from __future__ import annotations

from typing import Any

from eval.answers import Answer
from eval.oracle import OracleClassifier, attribute
from expense_validator.domain.models import ClassifierRequest

REQUEST = ClassifierRequest(description_clean="Red wine", merchant_name="Shop", mcc=5921)


def _answer() -> Answer:
    return Answer(
        receipt_id="SYN-1",
        disposition="flag",
        exceptions=(),
        signals=(),
        lines={"SYN-1-L1": {"category": "alcohol", "restricted": True}},
    )


def test_the_oracle_returns_the_answer_category_with_full_confidence() -> None:
    c = OracleClassifier({"SYN-1": _answer()}).classify("SYN-1-L1", REQUEST)
    assert c.status == "classified"
    assert (c.category, c.restricted, c.confidence) == ("alcohol", True, 1.0)
    assert (c.subtype, c.recipient_kind, c.recipient_name) == ("none", "none", None)
    assert c.source.classifier == "oracle"


def _row(rid: str, predicted: str, answer: str = "flag") -> dict[str, Any]:
    return {
        "receipt_id": rid,
        "scored": True,
        "predicted_disposition": predicted,
        "answer_disposition": answer,
    }


def test_attribution_maps_each_pair_to_its_stage() -> None:
    pipeline = [_row("A", "pass"), _row("B", "pass"), _row("C", "flag"), _row("D", "flag")]
    oracle = [_row("A", "flag"), _row("B", "pass"), _row("C", "pass"), _row("D", "flag")]
    out = attribute(pipeline, oracle)
    stages = {r["receipt_id"]: r["stage"] for r in out["rows"]}
    assert stages == {
        "A": "classification",
        "B": "rule_logic_or_convention",
        "C": "right_for_wrong_reason",
        "D": "none",
    }
    assert (out["oracle_accuracy"]["value"], out["oracle_accuracy"]["n"]) == (2, 4)
    assert (out["pipeline_accuracy"]["value"], out["pipeline_accuracy"]["n"]) == (2, 4)


def test_attribution_skips_out_of_scope_receipts() -> None:
    skipped = {**_row("Z", "pass"), "scored": False}
    out = attribute([_row("A", "flag"), skipped], [_row("A", "flag"), skipped])
    assert [r["receipt_id"] for r in out["rows"]] == ["A"]


def test_a_rule_the_oracle_cannot_fire_is_its_limitation_not_the_pipeline() -> None:
    pipeline = [{**_row("A", "flag"), "predicted_exceptions": [{"rule_id": "GIFT-04"}]}]
    oracle = [{**_row("A", "pass"), "predicted_exceptions": []}]
    assert attribute(pipeline, oracle)["rows"][0]["stage"] == "oracle_limitation"
