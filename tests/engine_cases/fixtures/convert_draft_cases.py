"""Convert explorations/dev_set/engine_cases_draft.jsonl into engine test fixtures (T045).

Splits each receipt into its input fields and a per-line classification, and adds the A6/A9
fields (subtype, recipient_kind, recipient_name) the drafts predate. Every added value that is
not the default is listed in CONVERSION_NOTES.md for Luis's review.
"""

import json
import sys
from pathlib import Path

src, out_dir = Path(sys.argv[1]), Path(sys.argv[2])
CLASSIFICATION_KEYS = ("category", "restricted", "confidence")
# Added from each case's own line text; reviewed by Luis before "MVP done" (SC-010).
ADDED = {
    "SYN-03-L1": {
        "recipient_kind": "government_official",
        "recipient_name": "Vice-Minister Ortega",
        "why": "The line text names 'Vice-Minister Ortega (Ministry of Trade)': a government "
        "official, so GIFT-04 applies to the meal line (A9).",
    },
}


def split(receipt: dict) -> dict:
    items, classifications = [], []
    for item in receipt["line_items"]:
        added = ADDED.get(item["line_id"], {})
        classifications.append(
            {
                "line_id": item["line_id"],
                "category": item["category"],
                "confidence": item["confidence"],
                "subtype": added.get("subtype", "none"),
                "recipient_kind": added.get("recipient_kind", "none"),
                "recipient_name": added.get("recipient_name"),
            }
        )
        items.append({k: v for k, v in item.items() if k not in CLASSIFICATION_KEYS})
    return {"receipt": {**receipt, "line_items": items}, "classifications": classifications}


cases, used = [], set()
for line in src.read_text(encoding="utf-8").splitlines():
    if not line.strip():
        continue
    case = json.loads(line)
    receipts = [split(case["receipt"])] + [split(r) for r in case.get("related_receipts") or []]
    used |= {c["line_id"] for r in receipts for c in r["classifications"]} & set(ADDED)
    cases.append(
        {
            "case_id": case["case_id"],
            "edge_case": case["edge_case"],
            "status": "DRAFT",
            "receipts": receipts,
            "expected": {
                "disposition": case["expected_disposition"],
                "exceptions": case["expected_exceptions"],
                "review_signals": [
                    s if isinstance(s, dict) else {"rule_id": s}
                    for s in case["expected_review_signals"]
                ],
            },
            "why": case.get("why"),
            "justification_quote": case.get("justification_quote"),
        }
    )
assert used == set(ADDED), used
out_dir.mkdir(parents=True, exist_ok=True)
(out_dir / "engine_cases.jsonl").write_text(
    "".join(json.dumps(c, ensure_ascii=False) + "\n" for c in cases), encoding="utf-8"
)
notes = [
    "# Conversion notes: synthetic engine cases (DRAFT)",
    "",
    "Source: `explorations/dev_set/engine_cases_draft.jsonl` (13 cases, written before decisions",
    "A6 and A9). Task T045 split each receipt into input fields and a per-line classification,",
    "and added `subtype`, `recipient_kind` and `recipient_name`. The default is `none`/`none`/null",
    "for every line; the values below are the only non-default additions. Expected outputs are",
    'unchanged. Luis reviews these before "MVP done" (SC-010, task T092).',
    "",
    "Regenerate with:",
    "",
    "```bash",
    "uv run python -I tests/engine_cases/fixtures/convert_draft_cases.py \\",
    "    explorations/dev_set/engine_cases_draft.jsonl tests/engine_cases/fixtures",
    "```",
    "",
    "| Line | Field | Value | Why |",
    "|---|---|---|---|",
]
for line_id, added in sorted(ADDED.items()):
    for field in ("subtype", "recipient_kind", "recipient_name"):
        if field in added:
            notes.append(f"| {line_id} | `{field}` | `{added[field]}` | {added['why']} |")
notes += ["", "## Resolutions of failing cases", "", "None yet.", ""]
(out_dir / "CONVERSION_NOTES.md").write_text("\n".join(notes), encoding="utf-8")
print(len(cases), "cases written")
