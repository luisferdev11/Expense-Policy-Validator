"""A classifier for load tests: a fixed answer, optionally after a sleep (spec 006, R13)."""

from __future__ import annotations

from expense_validator.adapters.simulated_classifier import LatencyClassifier, SimulatedClassifier
from expense_validator.domain.models import ClassifierRequest

REQ = ClassifierRequest(description_clean="Legal pads 3-pack", merchant_name="Supply", mcc=5943)


def test_it_answers_office_supplies_with_a_fixed_confidence_and_no_call() -> None:
    classifier = SimulatedClassifier()
    answer = classifier.classify("L1", REQ)
    assert (answer.status, answer.category, answer.confidence) == (
        "classified",
        "office_supplies",
        0.99,
    )
    assert answer.restricted is False
    assert answer.source.classifier == "simulated"
    assert classifier.calls_made == 0 and classifier.cache_hits == 0


def test_the_answer_keeps_the_line_id() -> None:
    assert SimulatedClassifier().classify("SYN-9-L2", REQ).line_id == "SYN-9-L2"


def test_a_latency_wrapper_sleeps_through_the_injected_function_then_answers() -> None:
    slept: list[float] = []
    inner = SimulatedClassifier()
    wrapped = LatencyClassifier(inner, 1500, sleep=slept.append)
    assert wrapped.classify("L1", REQ) == inner.classify("L1", REQ)
    assert slept == [1.5]


def test_the_wrapper_exposes_the_inner_metadata_and_counters() -> None:
    inner = SimulatedClassifier()
    wrapped = LatencyClassifier(inner, 0, sleep=lambda _: None)
    for attr in ("name", "model_id", "provider_endpoint", "prompt_version"):
        assert getattr(wrapped, attr) == getattr(inner, attr)
    assert wrapped.calls_made == 0 and wrapped.cache_hits == 0
