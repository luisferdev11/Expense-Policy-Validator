"""keyword-classifier baseline (T071, FR-032, research R11)."""

from expense_validator.classification.keyword import KEYWORDS, KeywordClassifier
from expense_validator.classification.port import ItemClassifier
from expense_validator.classification.taxonomy import CATEGORIES
from expense_validator.loader import load_receipts
from expense_validator.models import ClassifierRequest
from expense_validator.paths import TAXONOMY_FILE


def classify(text: str, mcc: int = 5999) -> str | None:
    req = ClassifierRequest(description_clean=text, merchant_name="M", mcc=mcc)
    return KeywordClassifier().classify("L1", req).category


def test_implements_the_port() -> None:
    assert isinstance(KeywordClassifier(), ItemClassifier)


def test_keyword_lists_use_taxonomy_categories_and_lowercase() -> None:
    assert set(KEYWORDS) <= set(CATEGORIES)
    for words in KEYWORDS.values():
        assert all(w == w.casefold() for w in words)


def test_matches_in_several_languages() -> None:
    assert classify("Red wine bottle") == "alcohol"
    assert classify("Cerveza grande") == "alcohol"
    assert classify("Bière pression") == "alcohol"
    assert classify("ワイン グラス") == "alcohol"
    assert classify("Taxi to airport") == "ground_transport"


def test_naive_on_purpose_names_lie() -> None:
    # The kind of system this project replaces: words, not meaning.
    assert classify("Beer-battered cod") == "alcohol"


def test_fallback_by_mcc() -> None:
    assert classify("Chef special", mcc=5812) == "food_beverage"
    assert classify("Unknown thing", mcc=5999) == "other"


def test_confidence_is_one_and_restricted_comes_from_the_taxonomy() -> None:
    req = ClassifierRequest(description_clean="Cigars", merchant_name="M", mcc=5993)
    c = KeywordClassifier().classify("L1", req)
    assert (c.category, c.restricted, c.confidence) == ("tobacco", True, 1.0)


def test_no_keyword_is_a_copy_of_a_real_description() -> None:
    """A keyword may equal a real one-word description only when the taxonomy itself, the
    stated source of the lists, contains it (e.g. "gratuity", "service charge")."""
    taxonomy = TAXONOMY_FILE.read_text(encoding="utf-8").casefold()
    descriptions = {
        item.description_raw.casefold() for r in load_receipts() for item in r.line_items
    }
    copies = [
        w for words in KEYWORDS.values() for w in words if w in descriptions and w not in taxonomy
    ]
    assert copies == []
