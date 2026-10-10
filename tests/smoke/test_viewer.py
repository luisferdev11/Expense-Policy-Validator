"""The viewer starts offline from committed outputs; its three views render (T043, T089)."""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from expense_validator.adapters.results_files import load_results
from expense_validator.paths import EVAL_DIR, RESULTS_FILE

APP = Path(__file__).resolve().parents[2] / "viewer" / "app.py"


def _app() -> AppTest:
    at = AppTest.from_file(str(APP), default_timeout=60)
    at.run()
    return at


def test_viewer_loads_without_errors() -> None:
    at = _app()
    assert not at.exception
    assert at.title[0].value == "Expense Policy Validator"


needs_outputs = pytest.mark.skipif(
    not (RESULTS_FILE.exists() and (EVAL_DIR / "metrics.json").exists()),
    reason="committed outputs not generated yet (task T090)",
)


@needs_outputs
def test_every_view_renders() -> None:
    at = _app()
    for view in ("Receipt list", "Receipt detail", "Metrics", "Experiments", "Upload"):
        at.sidebar.radio[0].set_value(view).run()
        assert not at.exception, view


@needs_outputs
def test_detail_matches_the_results_file() -> None:
    result = load_results()[-1]
    at = _app()
    at.sidebar.radio[0].set_value("Receipt detail").run()
    at.selectbox[0].set_value(result.receipt_id).run()
    assert not at.exception
    text = " ".join(m.value for m in at.markdown)
    for exc in result.exceptions:
        assert exc.rule_id in text
        assert exc.explanation in text
