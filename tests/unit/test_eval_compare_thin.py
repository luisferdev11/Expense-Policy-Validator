"""Thin evaluation: disposition matrix and out-of-scope exclusion (T040).

Predictions and answers are built here; nothing is read from data/receipts.jsonl.
"""

from eval.answers import Answer
from eval.compare import compare
from eval.metrics import confusion_matrix
from eval.scope import OUT_OF_SCOPE
from expense_validator.models import ReceiptResult, RunMetadata

RUN = RunMetadata(
    classifier="hand",
    model_id="m",
    provider_endpoint="e",
    prompt_version="p",
    rules_version="000000000000",
    exc03_threshold=0.5,
    exc03_threshold_status="provisional",
)


def result(rid: str, disposition: str) -> ReceiptResult:
    return ReceiptResult(
        receipt_id=rid,
        disposition=disposition,  # type: ignore[arg-type]
        line_items=[],
        exceptions=[],
        review_signals=[],
        run=RUN,
    )


def answer(rid: str, disposition: str) -> Answer:
    return Answer(receipt_id=rid, disposition=disposition, exceptions=(), signals=(), lines={})


def test_out_of_scope_set_is_the_four_timing_receipts() -> None:
    assert frozenset({"RCP-020", "RCP-021", "RCP-029", "RCP-030"}) == OUT_OF_SCOPE


def test_matrix_counts_and_excludes_out_of_scope() -> None:
    results = [
        result("SYN-A", "flag"),
        result("SYN-B", "review"),
        result("SYN-C", "pass"),
        result("SYN-D", "flag"),
        result("RCP-020", "flag"),
    ]
    answers = {
        "SYN-A": answer("SYN-A", "flag"),
        "SYN-B": answer("SYN-B", "flag"),
        "SYN-C": answer("SYN-C", "pass"),
        "SYN-D": answer("SYN-D", "pass"),
        "RCP-020": answer("RCP-020", "pass"),
    }
    rows = compare(results, answers)
    assert [r["scored"] for r in rows] == [False, True, True, True, True]
    m = confusion_matrix(rows)
    assert m["labels"] == ["flag", "review", "pass"]
    assert m["n"] == 4
    # rows = answer, columns = prediction
    assert m["matrix"] == [[1, 1, 0], [0, 0, 0], [1, 0, 1]]
