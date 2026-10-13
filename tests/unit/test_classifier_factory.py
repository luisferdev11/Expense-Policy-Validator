"""One factory builds the configured classifier (spec 007, T016, FR-024, FR-025)."""

from __future__ import annotations

from pathlib import Path

import pytest

from expense_validator.adapters.classification_cache import ClassificationCache
from expense_validator.adapters.hybrid_classifier import HybridClassifier
from expense_validator.adapters.openrouter.classifier import CAP_USD, OpenRouterClassifier
from expense_validator.adapters.openrouter.decision_classifier import DecisionClassifier
from expense_validator.adapters.openrouter.models import CLASSIFIER_NAMES, PINS
from expense_validator.adapters.tracing import GuardedTracer, NoopTracer
from expense_validator.app.classifiers import build_classifier, sync_prompt_links
from expense_validator.app.intake import default_classifier
from tests.fakes import RecordingTracer


@pytest.fixture
def cache(tmp_path: Path) -> ClassificationCache:
    return ClassificationCache(tmp_path / "c.jsonl")


@pytest.mark.parametrize("name", sorted(PINS))
def test_a_pin_builds_todays_chat_classifier(name: str, cache: ClassificationCache) -> None:
    tracer = RecordingTracer()
    clf = build_classifier(
        name,
        tracer,
        cache,
        offline=True,
        prompt_links={"chat": "CHAT-LINK", "decision": "DEC-LINK"},
        null_subtype_as_none=True,
    )
    assert isinstance(clf, OpenRouterClassifier)
    assert clf.pin == PINS[name]
    assert (clf.model_id, clf.provider_endpoint) == (PINS[name].model_id, "openrouter")
    assert clf.prompt_version == "cls-v2"
    assert clf.cache is cache and clf.tracer is tracer
    assert clf.offline is True and clf.null_subtype_as_none is True
    assert clf.prompt_link == "CHAT-LINK"
    assert clf.cap_usd == CAP_USD


def test_jev_builds_the_decision_classifier(cache: ClassificationCache) -> None:
    clf = build_classifier(
        "jev-1.13", RecordingTracer(), cache, prompt_links={"chat": "C", "decision": "D"}
    )
    assert isinstance(clf, DecisionClassifier)
    assert (clf.name, clf.model_id, clf.prompt_version) == (
        "openrouter-decision",
        "typesafe/jev-1.13",
        "dec-v1",
    )
    assert clf.prompt_link == "D"
    assert clf.cache is cache


def test_the_hybrid_pairs_jev_with_the_reference_on_one_cache(cache: ClassificationCache) -> None:
    clf = build_classifier(
        "jev-hybrid",
        RecordingTracer(),
        cache,
        prompt_links={"chat": "C", "decision": "D"},
        null_subtype_as_none=True,
        cap_usd=0.25,
    )
    assert isinstance(clf, HybridClassifier)
    assert isinstance(clf.category_source, DecisionClassifier)
    assert isinstance(clf.detail_source, OpenRouterClassifier)
    assert clf.detail_source.pin == PINS["gpt-oss-120b"]
    assert clf.category_source.cache is cache and clf.detail_source.cache is cache
    assert (clf.category_source.prompt_link, clf.detail_source.prompt_link) == ("D", "C")
    assert (clf.category_source.cap_usd, clf.detail_source.cap_usd) == (0.25, 0.25)
    assert clf.detail_source.null_subtype_as_none is True
    assert clf.cache is cache


def test_an_unknown_name_lists_the_accepted_ones(cache: ClassificationCache) -> None:
    with pytest.raises(ValueError) as info:
        build_classifier("gpt-9", RecordingTracer(), cache)
    message = str(info.value)
    assert "gpt-9" in message
    assert all(name in message for name in CLASSIFIER_NAMES)


def test_the_accepted_names_are_the_pins_jev_and_the_hybrid() -> None:
    assert set(CLASSIFIER_NAMES) == {*PINS, "jev-1.13", "jev-hybrid"}


def test_only_the_prompts_a_classifier_needs_are_synced() -> None:
    tracer = GuardedTracer(NoopTracer())
    assert set(sync_prompt_links("gpt-oss-120b", tracer, offline=False)) == {"chat"}
    assert set(sync_prompt_links("jev-1.13", tracer, offline=False)) == {"decision"}
    assert set(sync_prompt_links("jev-hybrid", tracer, offline=False)) == {"chat", "decision"}
    assert sync_prompt_links("jev-hybrid", tracer, offline=True) == {}


def test_the_default_classifier_follows_the_configured_name(tmp_path: Path) -> None:
    clf = default_classifier(RecordingTracer(), tmp_path / "upload.jsonl", offline=True)
    assert isinstance(clf, OpenRouterClassifier)  # config/pipeline.yaml stays gpt-oss-120b
    assert clf.model_id == "openai/gpt-oss-120b"
