"""The decision step shared by `epv run` and the worker (iteration 3, FR-016)."""

from __future__ import annotations

from expense_validator.adapters.config_files import load_settings
from expense_validator.adapters.tracing import NoopTracer
from expense_validator.app.decide import decide_receipt
from expense_validator.app.pipeline import run_metadata, run_pipeline
from expense_validator.domain.engine.context import build_context
from tests.factories import classified, item, receipt
from tests.fakes import FakeClassifier, RecordingTracer


def test_decide_receipt_equals_the_pipeline_result_for_the_same_receipt() -> None:
    r = receipt([item(1, description="Spiral notebook")])
    cr = classified(r, "office_supplies")
    clf = FakeClassifier({"Spiral notebook": cr.classifications[0]})
    settings = load_settings()
    meta = run_metadata(clf, settings)
    context = build_context([cr], settings)

    direct = decide_receipt(cr, context, meta, settings, NoopTracer(), "t")
    via_pipeline = run_pipeline([r], clf, NoopTracer(), settings, "t")

    assert [direct] == via_pipeline


def test_decide_receipt_records_the_three_spans_under_a_decide_trace() -> None:
    r = receipt([item(1, description="Spiral notebook")])
    cr = classified(r, "office_supplies")
    clf = FakeClassifier({"Spiral notebook": cr.classifications[0]})
    settings = load_settings()
    tracer = RecordingTracer()

    decide_receipt(
        cr, build_context([cr], settings), run_metadata(clf, settings), settings, tracer, "t"
    )

    assert [o.name for o in tracer.observations] == [
        "decide-receipt",
        "retrieve-rules",
        "apply-rules",
        "report-exceptions",
    ]
