"""Freezing the reviewed dev set (T010, research R2)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from eval.experiments.devset import freeze, load_frozen


def write(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


ITEMS = [
    {"item_id": "DEV-001", "description": "Glass of wine", "language": "en",
     "merchant_name": "Bistro", "mcc": 5812, "proposed_category": "alcohol",
     "restricted": True, "rationale": "r", "trap": None, "status": "DRAFT"},
    {"item_id": "DEV-002", "description": "Bracelet for a client", "language": "en",
     "merchant_name": "Jeweler", "mcc": 5944, "proposed_category": "jewelry",
     "restricted": True, "rationale": "r", "trap": "boundary:gift", "status": "DRAFT",
     "proposed_subtype": "none", "proposed_recipient_kind": "client_or_prospect",
     "proposed_recipient_name": None},
]  # fmt: skip


def review(item_id: str, label: str, **extra: Any) -> dict[str, Any]:
    return {"item_id": item_id, "draft_label": label, "reviewed_label": label,
            "decision": "confirmed", "reviewer": "Luis", "reviewed_at": "2026-10-09",
            "blind_to_model_outputs": True, "note": "", **extra}  # fmt: skip


def setup(tmp_path: Path, reviews: list[dict[str, Any]]) -> tuple[Path, Path, Path, Path]:
    items, revs = tmp_path / "items.jsonl", tmp_path / "reviews.jsonl"
    write(items, ITEMS)
    write(revs, reviews)
    return items, revs, tmp_path / "dev_set_v2.jsonl", tmp_path / "FROZEN.md"


def test_refuses_while_any_item_is_unreviewed(tmp_path: Path) -> None:
    items, revs, out, md = setup(tmp_path, [review("DEV-001", "alcohol")])
    with pytest.raises(ValueError, match="DEV-002"):
        freeze(items, revs, out, md, today="2026-10-09")


def test_applies_reviews_and_defaults(tmp_path: Path) -> None:
    reviews = [
        review("DEV-001", "food_beverage", decision="changed", note="mocktail"),
        review("DEV-002", "jewelry", reviewed_subtype="none",
               reviewed_recipient_kind="client_or_prospect", reviewed_recipient_name=None),
    ]  # fmt: skip
    items, revs, out, md = setup(tmp_path, reviews)
    digest = freeze(items, revs, out, md, today="2026-10-09")
    rows = load_frozen(out)
    assert rows[0]["category"] == "food_beverage" and rows[0]["restricted"] is False
    assert (rows[0]["subtype"], rows[0]["recipient_kind"], rows[0]["recipient_name"]) == (
        "none",
        "none",
        None,
    )
    assert rows[1]["recipient_kind"] == "client_or_prospect"
    assert (rows[0]["a6a9"], rows[1]["a6a9"]) == (False, True)
    assert rows[0]["review"] == "changed"
    assert digest == hashlib.sha256(out.read_bytes()).hexdigest()
    assert digest in md.read_text()


def test_the_last_review_of_an_item_wins_and_output_is_deterministic(tmp_path: Path) -> None:
    reviews = [review("DEV-001", "alcohol"), review("DEV-002", "jewelry"),
               review("DEV-001", "food_beverage", decision="changed", note="fixed")]  # fmt: skip
    items, revs, out, md = setup(tmp_path, reviews)
    first = freeze(items, revs, out, md, today="2026-10-09")
    assert load_frozen(out)[0]["category"] == "food_beverage"
    assert first == freeze(items, revs, out, md, today="2026-10-09")
