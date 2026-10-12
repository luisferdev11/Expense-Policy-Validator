"""The output schema is exported and the result invariants hold (T073, FR-018, FR-019, FR-023)."""

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from expense_validator.adapters.results_files import load_results
from expense_validator.app.composition import openapi_document
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


def _names(node: dict[str, Any], lookup: Callable[[str], dict[str, Any]]) -> Any:
    """Property names, recursively: follows `$ref`, `items` and the non-null side of `anyOf`."""
    while "$ref" in node:
        node = lookup(node["$ref"])
    alternatives = [alt for alt in node.get("anyOf", []) if alt.get("type") != "null"]
    if alternatives:
        return _names(alternatives[0], lookup)
    if node.get("type") == "array":
        return _names(node["items"], lookup)
    if "properties" in node:
        return {name: _names(sub, lookup) for name, sub in node["properties"].items()}
    return None


def test_the_apis_result_schema_has_the_property_names_of_the_spec_001_contract() -> None:
    """`ReceiptDetail.result` in the OpenAPI document names the same fields, at every depth
    (line items, exceptions, review signals, run), as the committed result contract (SC-006)."""
    document = openapi_document()
    contract = json.loads(SCHEMA_FILE.read_text(encoding="utf-8"))

    def in_document(ref: str) -> dict[str, Any]:
        return document["components"]["schemas"][ref.rsplit("/", 1)[1]]  # type: ignore[no-any-return]

    def in_contract(ref: str) -> dict[str, Any]:
        return contract["$defs"][ref.rsplit("/", 1)[1]]  # type: ignore[no-any-return]

    api_result = document["components"]["schemas"]["ReceiptDetail"]["properties"]["result"]
    api_names = _names(api_result, in_document)
    assert api_names is not None, "ReceiptDetail.result is still an untyped object"
    assert api_names == _names(contract, in_contract)
    assert set(api_names) == set(ReceiptResult.model_fields)
