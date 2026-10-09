"""Run experiment E13: every trial model over the dev set, through OpenRouter.

Usage: uv run --no-project --with openai --with python-dotenv --with requests \
           python explorations/scripts/run_e13.py [passes]

Models come from research/openrouter_models.json (the pre-registered list). Five models run in
parallel; each pass resumes where the last stopped and re-attempts transient provider errors, so
a second or third pass only fills gaps. Everything is cached, so re-running costs nothing.
"""

import contextlib
import io
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

EXP = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(EXP / "lib"))
import budget
import run_trial


def run_one(kind: str, model: str) -> str:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        run_trial.main(kind, model)
    rows = [json.loads(line) for line in run_trial.run_file(model).read_text().splitlines()]
    errors = sum(1 for r in rows if r.get("error"))
    return f"{model:<34} {len(rows):>3} rows, {errors} errors"


def main(passes: int) -> None:
    models = json.loads(budget.MODELS_SNAPSHOT.read_text())["models"]
    for p in range(1, passes + 1):
        print(f"pass {p}", flush=True)
        with ThreadPoolExecutor(max_workers=5) as pool:
            for line in pool.map(lambda kv: run_one(kv[1]["kind"], kv[0]), models.items()):
                print("  " + line, flush=True)
    print(json.dumps(budget.spend_report(measure=True), indent=1))


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 3)
