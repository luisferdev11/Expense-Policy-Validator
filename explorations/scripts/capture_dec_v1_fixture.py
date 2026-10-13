"""Capture the `dec-v1` decision payload for three synthetic items, once (spec 007, T002).

    uv run python -I explorations/scripts/capture_dec_v1_fixture.py

`explorations/lib/decision_adapters.py` built the payload that E13 and the 2026-10-11 jev run sent.
The package now carries its own copy (`adapters/openrouter/decision_prompt.py`), and
`tests/fixtures/dec_v1_payload.json` pins that this copy equals the exploration's for these items,
so the dev-set evidence for jev stays valid. The merchants, MCCs and texts are invented; no dev or
receipt data is read, and no model is called.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT / "explorations" / "lib"))

import decision_adapters as da  # frozen research code, read-only

ITEMS = [
    {
        "description": "grilled chicken sandwich with fries",
        "merchant_name": "Harbor Street Diner",
        "mcc": 5812,
    },
    {
        "description": "ワイヤレス充電器",
        "merchant_name": "Sakura Denki Shop",
        "mcc": 5732,
    },
    {
        "description": "Moscow Mule copper mug",
        "merchant_name": "Alder and Finch Home",
        "mcc": 5719,
    },
]


def main() -> None:
    document = {
        "prompt_version": da.DECISION_PROMPT_VERSION,
        "source": "explorations/lib/decision_adapters.py, captured by this script",
        "items": [
            {
                "description_clean": item["description"],
                "merchant_name": item["merchant_name"],
                "mcc": item["mcc"],
                "payload": da.decision_payload(item),
            }
            for item in ITEMS
        ],
    }
    target = ROOT / "tests" / "fixtures" / "dec_v1_payload.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(document, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"wrote {target.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
