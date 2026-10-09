"""Report which synthetic dev items are too similar to a real description.

Prints only synthetic item IDs, their own descriptions and scores; real descriptions are never
printed. Real descriptions come through the label-stripping loader.
"""

import difflib
import sys
from pathlib import Path

EXP = Path(__file__).resolve().parent.parent  # explorations/
sys.path.insert(0, str(EXP / "lib"))
from receipts_safe import load_inputs

src = (EXP / "notebooks" / "src" / "03_synthetic_dev_set.py").read_text()
block = src[src.index("ITEMS = [") : src.index('print(len(ITEMS), "items")')]
ns: dict = {}
exec(block, ns)
real = [i["description_raw"].lower() for r in load_inputs() for i in r["line_items"]]
threshold = float(sys.argv[1]) if len(sys.argv) > 1 else 0.75
for n, item in enumerate(ns["ITEMS"], start=1):
    d = item[0].lower()
    score = max(difflib.SequenceMatcher(None, d, x).ratio() for x in real)
    if score >= threshold:
        print(f"DEV-{n:03d}  {score:.3f}  {item[0]}")
