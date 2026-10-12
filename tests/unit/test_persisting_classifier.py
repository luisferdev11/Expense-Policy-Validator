"""A billed answer is saved the moment it is paid for, so a crash never bills it twice.

The batch run saves the cache once at the end. A worker can be killed at any line, so it saves
after every billed call, and the file is replaced atomically so a crash cannot truncate it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from expense_validator.adapters.classification_cache import ClassificationCache
from expense_validator.adapters.persisting_classifier import PersistingClassifier
from expense_validator.domain.models import CacheEntry, ClassifierRequest
from tests.fakes import BillingClassifier

REQ = ClassifierRequest(description_clean="Spiral notebook", merchant_name="M", mcc=5943)


def entry(key: str) -> CacheEntry:
    return CacheEntry(
        cache_key=key,
        content="{}",
        model_id="m",
        provider_endpoint="e",
        prompt_version="p",
        request_id=None,
        cost_usd=None,
        prompt_tokens=None,
        completion_tokens=None,
        reasoning=None,
    )


def test_saving_replaces_the_file_atomically_and_leaves_no_temporary_file(tmp_path: Path) -> None:
    cache = ClassificationCache(tmp_path / "cache.jsonl")
    cache.put(entry("a"))
    cache.save()
    cache.put(entry("b"))
    cache.save()
    assert sorted(p.name for p in tmp_path.iterdir()) == ["cache.jsonl"]
    assert len(ClassificationCache(tmp_path / "cache.jsonl")) == 2


def test_the_cache_is_saved_after_a_billed_call_and_not_after_a_hit() -> None:
    saves: list[int] = []
    inner = BillingClassifier({"Spiral notebook": "office_supplies"})
    wrapped = PersistingClassifier(inner, lambda: saves.append(1))
    wrapped.classify("L1", REQ)
    assert saves == [1] and wrapped.calls_made == 1
    wrapped.classify("L2", REQ)  # answered from the cache: nothing to persist
    assert saves == [1] and wrapped.cache_hits == 1


def test_the_wrapper_keeps_the_identity_of_the_classifier_it_wraps() -> None:
    inner = BillingClassifier({})
    wrapped = PersistingClassifier(inner, lambda: None)
    assert (wrapped.name, wrapped.model_id, wrapped.provider_endpoint, wrapped.prompt_version) == (
        inner.name,
        inner.model_id,
        inner.provider_endpoint,
        inner.prompt_version,
    )


def test_a_classifier_that_raises_does_not_save() -> None:
    saves: list[int] = []
    wrapped = PersistingClassifier(
        BillingClassifier({}, fail_with=RuntimeError("down")), lambda: saves.append(1)
    )
    with pytest.raises(RuntimeError):
        wrapped.classify("L1", REQ)
    assert saves == []
