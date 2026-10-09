"""Matching rules from data/README.md (T079, FR-031)."""

from typing import Any

from eval.metrics import evidence_correctness, exc03_effect, per_rule, reg04_vat_only


def r(  # type: ignore[no-untyped-def]
    predicted: list[dict[str, Any]],
    answer: list[dict[str, Any]],
    signals: list[dict[str, Any]] | None = None,
    pred_disp: str = "flag",
    scored: bool = True,
):
    return {
        "receipt_id": "SYN",
        "scored": scored,
        "predicted_exceptions": predicted,
        "answer_exceptions": answer,
        "predicted_signals": signals or [],
        "answer_signals": [],
        "predicted_disposition": pred_disp,
        "answer_disposition": "flag",
        "lines": [],
    }


def e(rule: str, lines: list[str], severity: str = "medium", **extra: Any) -> dict[str, Any]:
    return {"rule_id": rule, "line_ids": lines, "severity": severity, **extra}


def test_per_rule_matches_on_receipt_and_rule_id() -> None:
    rows = [
        r([e("TECH-02", ["L1"]), e("MCC-01", [])], [e("TECH-02", ["L2"]), e("ALC-01", ["L3"])]),
        r([e("TECH-02", ["L1"])], []),
    ]
    rules = per_rule(rows)
    assert rules["TECH-02"] == {"tp": 1, "fp": 1, "fn": 0, "precision": 0.5, "recall": 1.0}
    assert rules["ALC-01"] == {"tp": 0, "fp": 0, "fn": 1, "precision": None, "recall": 0.0}
    assert rules["MCC-01"] == {"tp": 0, "fp": 1, "fn": 0, "precision": 0.0, "recall": None}


def test_evidence_correctness_over_matched_exceptions_only() -> None:
    rows = [
        r(
            [e("TECH-02", ["L1"]), e("DOC-03", []), e("PERS-02", ["L1", "L2"])],
            [e("TECH-02", ["L2"]), e("DOC-03", []), e("PERS-02", ["L2", "L1"])],
        )
    ]
    m = evidence_correctness(rows)
    assert (m["value"], m["n"]) == (2, 3)  # line order does not matter; sets are compared


def test_exc03_effect_counts_signals_and_changed_dispositions() -> None:
    rows = [
        r([], [], signals=[{"rule_id": "EXC-03", "line_ids": ["L1"]}], pred_disp="review"),
        r([e("TECH-02", ["L1"])], [], [{"rule_id": "EXC-03", "line_ids": ["L2"]}]),
        r([], [], [{"rule_id": "EXC-03", "line_ids": ["L1"]}, {"rule_id": "MCC-02"}], "review"),
    ]
    effect = exc03_effect(rows)
    assert effect == {"signals": 3, "receipts": 3, "dispositions_changed": 1}


def test_reg04_exceptions_from_the_absent_vat_field() -> None:
    rows = [
        r([e("REG-04", [], "low", computed={"vat_number": "not recorded"})], []),
        r([e("TECH-02", ["L1"])], []),
    ]
    m = reg04_vat_only(rows)
    assert (m["value"], m["n"]) == (1, 1)


def test_unscored_rows_are_ignored() -> None:
    rows = [r([e("TECH-02", ["L1"])], [], scored=False)]
    assert per_rule(rows) == {}
