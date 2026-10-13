"""config/pipeline.yaml carries the iteration 2 winners into the run (T025, research R11)."""

from __future__ import annotations

from pathlib import Path

import pytest

from expense_validator.adapters.config_files import (
    PIPELINE_FILE,
    load_pipeline_config,
    load_settings,
)
from expense_validator.adapters.openrouter.models import CLASSIFIER_NAMES, PINS
from expense_validator.app.pipeline import run_metadata


def test_the_winners_are_configured() -> None:
    c = load_pipeline_config()
    assert c.classifier_model == "gpt-oss-120b"
    assert c.classifier_model in PINS
    assert c.confidence_source == "self_reported"
    assert c.translate is False
    assert c.null_subtype_as_none is False
    assert len(c.version) == 12


def _config_with(tmp_path: Path, classifier_model: str) -> Path:
    text = PIPELINE_FILE.read_text(encoding="utf-8").replace(
        "classifier_model: gpt-oss-120b", f"classifier_model: {classifier_model}"
    )
    assert f"classifier_model: {classifier_model}" in text
    path = tmp_path / "pipeline.yaml"
    path.write_text(text, encoding="utf-8")
    return path


@pytest.mark.parametrize("name", CLASSIFIER_NAMES)
def test_every_factory_name_is_accepted(tmp_path: Path, name: str) -> None:
    assert load_pipeline_config(_config_with(tmp_path, name)).classifier_model == name


def test_an_unknown_classifier_is_rejected_with_the_accepted_names(tmp_path: Path) -> None:
    with pytest.raises(ValueError) as info:
        load_pipeline_config(_config_with(tmp_path, "gpt-9"))
    assert "gpt-9" in str(info.value)
    assert all(name in str(info.value) for name in CLASSIFIER_NAMES)


def test_the_committed_classifier_is_still_the_reference() -> None:
    assert load_pipeline_config().classifier_model == "gpt-oss-120b"


class _Clf:
    name = "openrouter"
    model_id = "openai/gpt-oss-120b"
    provider_endpoint = "openrouter"
    prompt_version = "cls-v2"

    def classify(self, line_id: str, request: object) -> object:
        raise NotImplementedError


def test_run_metadata_records_the_configuration() -> None:
    config = load_pipeline_config()
    meta = run_metadata(_Clf(), load_settings(), config)  # type: ignore[arg-type]
    assert meta.confidence_source == "self_reported"
    assert meta.pipeline_config_version == config.version
    assert meta.exc03_threshold == 0.97
    assert meta.exc03_threshold_status == "chosen_on_dev"
