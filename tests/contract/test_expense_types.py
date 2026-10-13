"""The declared expense types the intake form suggests equal the ones the engine knows (spec 008).

`frontend/src/samples/expense-types.json` is a suggestion list for the form. It must not drift from
`COVERS` (documentation rules) and `MEAL_TYPES` (context). The engine is only imported here.
Regenerate the file with `uv run python -m tests.contract.test_expense_types`.
"""

import json
from pathlib import Path

from expense_validator.domain.engine.context import MEAL_TYPES
from expense_validator.domain.engine.rules.documentation import COVERS

TYPES_FILE = (
    Path(__file__).resolve().parents[2] / "frontend" / "src" / "samples" / "expense-types.json"
)


def engine_types() -> list[str]:
    return sorted(set(COVERS) | MEAL_TYPES)


def test_form_suggestions_match_the_engine() -> None:
    committed = json.loads(TYPES_FILE.read_text(encoding="utf-8"))
    assert committed == engine_types(), (
        "frontend/src/samples/expense-types.json drifted from the engine; "
        "run `uv run python -m tests.contract.test_expense_types` to regenerate it"
    )


if __name__ == "__main__":
    TYPES_FILE.write_text(json.dumps(engine_types(), indent=2) + "\n", encoding="utf-8")
    print(f"wrote {len(engine_types())} types to {TYPES_FILE}")
