"""The frozen dev set: Luis's reviews applied to the synthetic items, then hashed (research R2).

Refuses to freeze while any item is unreviewed. A6/A9 fields default to none/none/null unless an
item proposed them and the review confirmed or changed them. The last review of an item wins.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from expense_validator.domain.taxonomy import restricted_for
from expense_validator.paths import REPO_ROOT

DEV_DIR = REPO_ROOT / "explorations" / "dev_set"
ITEMS = DEV_DIR / "dev_items_draft.jsonl"
REVIEWS = DEV_DIR / "label_reviews.jsonl"
FROZEN = DEV_DIR / "dev_set_v2.jsonl"
FROZEN_MD = DEV_DIR / "FROZEN.md"


def _jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def freeze(
    items_path: Path = ITEMS,
    reviews_path: Path = REVIEWS,
    out_path: Path = FROZEN,
    md_path: Path = FROZEN_MD,
    today: str = "",
) -> str:
    items = _jsonl(items_path)
    reviews = {r["item_id"]: r for r in _jsonl(reviews_path)}
    missing = [i["item_id"] for i in items if i["item_id"] not in reviews]
    if missing:
        raise ValueError(f"{len(missing)} items are not reviewed yet: {', '.join(missing)}")
    rows = []
    for item in items:
        r = reviews[item["item_id"]]
        category = r["reviewed_label"]
        rows.append(
            {
                "item_id": item["item_id"],
                "description": item["description"],
                "language": item["language"],
                "merchant_name": item["merchant_name"],
                "mcc": item["mcc"],
                "category": category,
                "restricted": restricted_for(category),
                "subtype": r.get("reviewed_subtype", item.get("proposed_subtype", "none")),
                "recipient_kind": r.get(
                    "reviewed_recipient_kind", item.get("proposed_recipient_kind", "none")
                ),
                "recipient_name": r.get(
                    "reviewed_recipient_name", item.get("proposed_recipient_name")
                ),
                "review": r["decision"],
                "a6a9": "proposed_recipient_kind" in item or "proposed_subtype" in item,
                "trap": item.get("trap"),
            }
        )
    out_path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8"
    )
    digest = hashlib.sha256(out_path.read_bytes()).hexdigest()
    changed = sum(1 for row in rows if row["review"] == "changed")
    md_path.write_text(
        "# Frozen dev set\n\n"
        f"- File: `{out_path.name}`\n"
        f"- SHA-256: `{digest}`\n"
        f"- Items: {len(rows)}, all reviewed by Luis blind to model outputs; {changed} changed\n"
        f"- Frozen on: {today}\n"
        "- All items decide (iteration 2 clarification); prompt cls-v2 is frozen.\n",
        encoding="utf-8",
    )
    return digest


def load_frozen(path: Path = FROZEN) -> list[dict[str, Any]]:
    return _jsonl(path)


def frozen_hash(path: Path = FROZEN) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
