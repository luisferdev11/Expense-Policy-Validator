"""config/pipeline.yaml carries the iteration 2 winners into the run (T025, research R11)."""

from __future__ import annotations

from expense_validator.adapters.config_files import load_pipeline_config, load_settings
from expense_validator.adapters.openrouter.models import PINS
from expense_validator.app.pipeline import run_metadata


def test_the_winners_are_configured() -> None:
    c = load_pipeline_config()
    assert c.classifier_model == "gpt-oss-120b"
    assert c.classifier_model in PINS
    assert c.confidence_source == "self_reported"
    assert c.translate is False
    assert c.null_subtype_as_none is False
    assert len(c.version) == 12


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
