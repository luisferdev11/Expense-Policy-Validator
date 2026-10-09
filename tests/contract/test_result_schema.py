"""The output schema is exported and the result invariants hold (T073, FR-018, FR-019, FR-023)."""

import json
from pathlib import Path

from expense_validator.adapters.results_files import load_results
from expense_validator.domain.engine.registry import REGISTRY
from expense_validator.domain.models import ReceiptResult
from expense_validator.paths import POLICY_DIR, RESULTS_FILE

SCHEMA_FILE = (
    Path(__file__).resolve().parents[2]
    / "specs"
    / "001-mvp-end-to-end"
    / "contracts"
    / "receipt-result.schema.json"
)
WHOLE_RECEIPT = {
    "MCC-01", "MEAL-01", "MEAL-02", "DOC-01", "DOC-02", "DOC-03", "DOC-04",
    "REG-02", "REG-03", "REG-04",
}  # fmt: skip
BRIEF_FIELDS = {"receipt_id", "disposition", "line_items", "exceptions", "review_signals"}


def test_exported_schema_has_not_drifted() -> None:
    exported = ReceiptResult.model_json_schema()
    assert json.loads(SCHEMA_FILE.read_text(encoding="utf-8")) == exported


def test_brief_fields_are_present() -> None:
    assert set(ReceiptResult.model_fields) >= BRIEF_FIELDS


def test_invariants_on_committed_results() -> None:
    results = load_results(RESULTS_FILE)
    for r in results:
        rule_ids = [e.rule_id for e in r.exceptions]
        assert len(rule_ids) == len(set(rule_ids)), r.receipt_id
        fees = {line.line_id for line in r.line_items if line.category == "service_fee"}
        for e in r.exceptions:
            assert e.rule_id in REGISTRY
            if e.rule_id in WHOLE_RECEIPT:
                assert e.line_ids == [], (r.receipt_id, e.rule_id)
            assert not set(e.line_ids) & fees, (r.receipt_id, e.rule_id)
            doc = " ".join((POLICY_DIR / e.policy_doc).read_text(encoding="utf-8").split())
            assert " ".join(e.evidence.split()) in doc.replace("**", "")
