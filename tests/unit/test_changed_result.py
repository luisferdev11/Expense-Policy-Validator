"""What counts as a changed result, and the quality-review sample (ADR 0007 D7 and D12)."""

from __future__ import annotations

from expense_validator.adapters.config_files import load_settings
from expense_validator.adapters.tracing import NoopTracer
from expense_validator.app.decide import decide_receipt
from expense_validator.app.pipeline import run_metadata
from expense_validator.domain.engine.context import build_context
from expense_validator.domain.evaluation import result_hash
from expense_validator.domain.models import ClassifiedReceipt, ReceiptResult
from expense_validator.domain.review import QA_SAMPLE_ONE_IN, qa_sampled
from tests.factories import classified, item, receipt
from tests.fakes import FakeClassifier


def _result(cr: ClassifiedReceipt) -> ReceiptResult:
    settings = load_settings()
    clf = FakeClassifier({})
    return decide_receipt(
        cr,
        build_context([cr], settings),
        run_metadata(clf, settings),
        settings,
        NoopTracer(),
        "t",
    )


def test_the_same_classified_receipt_gives_the_same_hash() -> None:
    cr = classified(receipt([item(1)]), "office_supplies")
    assert result_hash(_result(cr)) == result_hash(_result(cr))


def test_a_different_category_changes_the_hash_even_when_the_findings_are_equal() -> None:
    base = _result(classified(receipt([item(1)]), "office_supplies"))
    line = base.line_items[0].model_copy(update={"category": "lodging"})
    recategorised = base.model_copy(update={"line_items": [line]})
    assert recategorised.exceptions == base.exceptions  # same findings...
    assert result_hash(recategorised) != result_hash(base)  # ...but a different classification


def test_new_findings_change_the_hash() -> None:
    r = receipt([item(1)])
    office = _result(classified(r, "office_supplies"))
    software = _result(classified(r, "software_subscription"))
    assert office.exceptions != software.exceptions
    assert result_hash(software) != result_hash(office)


def test_the_run_metadata_does_not_change_the_hash() -> None:
    cr = classified(receipt([item(1)]), "office_supplies")
    base = _result(cr)
    other = base.model_copy(update={"run": base.run.model_copy(update={"model_id": "elsewhere"})})
    assert result_hash(base) == result_hash(other)


def test_the_qa_sample_is_deterministic_and_about_one_in_ten() -> None:
    assert qa_sampled("R-1", 1) == qa_sampled("R-1", 1)
    sampled = sum(qa_sampled(f"R-{n}", 1) for n in range(2000))
    assert QA_SAMPLE_ONE_IN == 10
    assert 140 <= sampled <= 260


def test_the_sample_depends_on_the_revision() -> None:
    picks = {qa_sampled("R-1", n) for n in range(1, 60)}
    assert picks == {True, False}
