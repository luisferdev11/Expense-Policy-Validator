"""Label review for the synthetic dev set: one item at a time, blind to every model output.

Run from the repository root:

    uv run streamlit run explorations/review/label_review_app.py

It reads only `explorations/dev_set/dev_items_draft.jsonl` and the existing reviews. It never
reads model predictions, trial results or `data/receipts.jsonl`. Each decision is appended to
`explorations/dev_set/label_reviews.jsonl` in the format of the first eight reviews. Items that
propose a subtype or recipient (decisions A6 and A9) show those fields for review too.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

import streamlit as st

ROOT = Path(__file__).resolve().parents[2]
ITEMS = ROOT / "explorations" / "dev_set" / "dev_items_draft.jsonl"
REVIEWS = ROOT / "explorations" / "dev_set" / "label_reviews.jsonl"
TAXONOMY = ROOT / "data" / "category-taxonomy.md"
REVIEWER = "Luis"
SUBTYPES = ["none", "event_ticket", "mobile_handset", "prescription_medication"]
RECIPIENTS = ["none", "client_or_prospect", "employee", "government_official"]


def _jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _categories() -> list[str]:
    rows = TAXONOMY.read_text(encoding="utf-8").splitlines()
    return [r.split("`")[1] for r in rows if r.startswith("| `")]


def _append(review: dict[str, Any]) -> None:
    with REVIEWS.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(review, ensure_ascii=False) + "\n")


st.set_page_config(page_title="Dev label review", layout="centered")
st.title("Dev label review")
st.caption("Blind to model outputs: only the item and its draft label are shown.")

items = _jsonl(ITEMS)
reviewed = {r["item_id"] for r in _jsonl(REVIEWS)}
pending = [i for i in items if i["item_id"] not in reviewed]
st.progress(
    1 - len(pending) / len(items), text=f"{len(items) - len(pending)} of {len(items)} reviewed"
)

if not pending:
    st.success("Every item is reviewed.")
    st.stop()

skip = st.session_state.setdefault("skip", 0) % len(pending)
item = pending[skip]
categories = _categories()

st.subheader(item["item_id"])
st.markdown(f"### {item['description']}")
st.markdown(
    f"**Language:** `{item['language']}` · **Merchant:** {item['merchant_name']} · "
    f"**MCC:** {item['mcc']}"
)
st.markdown(f"**Draft label:** `{item['proposed_category']}`")
st.caption(f"Draft rationale: {item.get('rationale') or '—'}")
if item.get("a6_a9_rationale") and item.get("a6_a9_rationale") != item.get("rationale"):
    st.caption(f"Subtype and recipient rationale: {item['a6_a9_rationale']}")
if item.get("trap"):
    st.caption(f"Trap: {item['trap']}")

with st.form(key=f"form-{item['item_id']}"):
    label = st.selectbox(
        "Correct category", categories, index=categories.index(item["proposed_category"])
    )
    subtype = recipient_kind = None
    if "proposed_subtype" in item:
        subtype = st.selectbox(
            "Subtype (A6)", SUBTYPES, index=SUBTYPES.index(item["proposed_subtype"])
        )
    if "proposed_recipient_kind" in item:
        recipient_kind = st.selectbox(
            "Recipient kind (A9)",
            RECIPIENTS,
            index=RECIPIENTS.index(item["proposed_recipient_kind"]),
        )
    recipient_name = None
    if "proposed_recipient_kind" in item:
        recipient_name = st.text_input(
            "Recipient name (A9: a proper name only; leave empty if the line names no one)",
            value=item.get("proposed_recipient_name") or "",
        ).strip()
    note = st.text_input("Note (optional; required when you change something)")
    saved = st.form_submit_button("Save and next", type="primary")

if saved:
    changed = label != item["proposed_category"]
    changed |= subtype is not None and subtype != item.get("proposed_subtype")
    changed |= recipient_kind is not None and recipient_kind != item.get("proposed_recipient_kind")
    changed |= recipient_name is not None and (recipient_name or None) != item.get(
        "proposed_recipient_name"
    )
    if changed and not note.strip():
        st.error("Add a note saying why the label changes.")
    else:
        review: dict[str, Any] = {
            "item_id": item["item_id"],
            "draft_label": item["proposed_category"],
            "reviewed_label": label,
            "decision": "changed" if changed else "confirmed",
            "reviewer": REVIEWER,
            "reviewed_at": date.today().isoformat(),
            "blind_to_model_outputs": True,
            "note": note.strip(),
        }
        if subtype is not None:
            review |= {"draft_subtype": item["proposed_subtype"], "reviewed_subtype": subtype}
        if recipient_kind is not None:
            review |= {
                "draft_recipient_kind": item["proposed_recipient_kind"],
                "reviewed_recipient_kind": recipient_kind,
                "draft_recipient_name": item.get("proposed_recipient_name"),
                "reviewed_recipient_name": recipient_name or None,
            }
        _append(review)
        st.rerun()

if st.button("Skip for now"):
    st.session_state["skip"] = skip + 1
    st.rerun()

with st.expander("Taxonomy (data/category-taxonomy.md)"):
    st.markdown(TAXONOMY.read_text(encoding="utf-8"))
