"""Committed classification cache (T025, FR-008, research R5)."""

from pathlib import Path

from expense_validator.adapters.classification_cache import ClassificationCache, cache_key
from expense_validator.domain.models import CacheEntry, ClassifierRequest

REQ = ClassifierRequest(description_clean="Coffee", merchant_name="Cafe", mcc=5812)


def entry(key: str, cost: float = 0.0001) -> CacheEntry:
    return CacheEntry(
        cache_key=key,
        content='{"category": "food_beverage", "confidence": 0.9, "subtype": "none", '
        '"recipient_kind": "none", "recipient_name": null}',
        model_id="m",
        provider_endpoint="e",
        prompt_version="p",
        request_id="gen-1",
        cost_usd=cost,
        prompt_tokens=10,
        completion_tokens=5,
        reasoning="short",
    )


def test_key_changes_with_every_input() -> None:
    base = cache_key(REQ, "m", "e", "p")
    assert base == cache_key(REQ, "m", "e", "p")
    assert len(base) == 64
    variants = {
        cache_key(REQ.model_copy(update={"description_clean": "Tea"}), "m", "e", "p"),
        cache_key(REQ.model_copy(update={"merchant_name": "Other"}), "m", "e", "p"),
        cache_key(REQ.model_copy(update={"mcc": 5813}), "m", "e", "p"),
        cache_key(REQ, "m2", "e", "p"),
        cache_key(REQ, "m", "e2", "p"),
        cache_key(REQ, "m", "e", "p2"),
    }
    assert base not in variants
    assert len(variants) == 6


def test_rows_are_sorted_and_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "classifications.jsonl"
    cache = ClassificationCache(path)
    cache.put(entry("b" * 64))
    cache.put(entry("a" * 64))
    cache.save()
    text = path.read_text(encoding="utf-8")
    assert text.endswith("\n")
    assert text.index("a" * 64) < text.index("b" * 64)
    again = ClassificationCache(path)
    assert again.get("a" * 64) == entry("a" * 64)
    again.save()
    assert path.read_text(encoding="utf-8") == text


def test_total_cost(tmp_path: Path) -> None:
    cache = ClassificationCache(tmp_path / "c.jsonl")
    cache.put(entry("a" * 64, 0.25))
    cache.put(entry("b" * 64, 0.5))
    assert cache.total_cost_usd() == 0.75


def test_missing_file_is_an_empty_cache(tmp_path: Path) -> None:
    assert ClassificationCache(tmp_path / "none.jsonl").get("x") is None
