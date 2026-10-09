"""The viewer starts offline from committed outputs (T043)."""

from pathlib import Path

from streamlit.testing.v1 import AppTest

APP = Path(__file__).resolve().parents[2] / "viewer" / "app.py"


def test_viewer_loads_without_errors() -> None:
    at = AppTest.from_file(str(APP), default_timeout=60)
    at.run()
    assert not at.exception
    assert at.title[0].value == "Expense Policy Validator"
