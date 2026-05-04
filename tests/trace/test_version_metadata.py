from __future__ import annotations

from services.trace import (
    LEDGER_SCHEMA_VERSION,
    MACRO_CALCULATOR_VERSION,
    MATCHER_VERSION,
    NUTRITION_CATALOG_VERSION,
    PORTION_ENGINE_VERSION,
    VISION_SCHEMA_VERSION,
    build_trace_version_metadata,
    prompt_sha256,
)


def test_build_trace_version_metadata_uses_stable_version_constants() -> None:
    metadata = build_trace_version_metadata(
        vision_model_name="trace-test-model",
        vision_prompt_text="trace prompt text",
    )

    assert metadata.vision_schema_version == VISION_SCHEMA_VERSION
    assert metadata.vision_model_name == "trace-test-model"
    assert metadata.vision_prompt_hash == prompt_sha256("trace prompt text")
    assert metadata.nutrition_catalog_version == NUTRITION_CATALOG_VERSION
    assert metadata.matcher_version == MATCHER_VERSION
    assert metadata.portion_engine_version == PORTION_ENGINE_VERSION
    assert metadata.macro_calculator_version == MACRO_CALCULATOR_VERSION
    assert metadata.ledger_schema_version == LEDGER_SCHEMA_VERSION


def test_prompt_sha256_is_deterministic_and_input_sensitive() -> None:
    baseline = prompt_sha256("trace prompt text")

    assert baseline == prompt_sha256("trace prompt text")
    assert baseline != prompt_sha256("trace prompt text changed")
