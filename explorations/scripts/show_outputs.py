"""Print the text outputs (stdout and plain-text results) of an executed notebook."""

import json
import sys
from pathlib import Path

nb = json.loads(Path(sys.argv[1]).read_text())
limit = int(sys.argv[2]) if len(sys.argv) > 2 else 1500
for i, cell in enumerate(nb["cells"]):
    if cell["cell_type"] != "code":
        continue
    for out in cell.get("outputs", []):
        text = out.get("text") or out.get("data", {}).get("text/plain")
        if text:
            print(f"--- cell {i} ---")
            print("".join(text)[:limit])
