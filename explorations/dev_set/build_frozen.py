"""Freeze the reviewed dev set: uv run python -I explorations/dev_set/build_frozen.py

Writes dev_set_v2.jsonl and FROZEN.md next to this file. It refuses while any item is
unreviewed. The logic lives in eval/experiments/devset.py, where it is tested.
"""

from datetime import date

from eval.experiments.devset import freeze

if __name__ == "__main__":
    print("frozen, sha256:", freeze(today=date.today().isoformat()))
