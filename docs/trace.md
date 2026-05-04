# Trace Version Metadata

`services.nutrition.src.version_metadata` is the single source of truth for stable meal-trace version identifiers.

## Stable Constants

- `VISION_SCHEMA_VERSION`: the structured vision response schema version
- `VISION_MODEL_NAME`: the default vision model name used for traces
- `VISION_PROMPT_TEXT`: the default vision prompt text used to derive the prompt hash
- `NUTRITION_CATALOG_VERSION`: the nutrition catalog version used by matching
- `MATCHER_VERSION`: the local matcher version
- `PORTION_ENGINE_VERSION`: the portion parser / engine version
- `MACRO_CALCULATOR_VERSION`: the macro calculator version
- `LEDGER_SCHEMA_VERSION`: the SQLite ledger schema version

## Trace Model

`TraceVersionMetadata` records:

- `vision_schema_version`
- `vision_model_name`
- `vision_prompt_hash`
- `nutrition_catalog_version`
- `matcher_version`
- `portion_engine_version`
- `macro_calculator_version`
- `ledger_schema_version`

`build_trace_version_metadata()` computes the SHA-256 prompt hash and returns the canonical frozen model used throughout the pipeline.
`DEFAULT_TRACE_VERSION_METADATA` is the default value used for legacy or injected inputs that do not already carry trace metadata.

## Where It Appears

- `VisionAnalysisResponse.trace_versions`
- `MealEstimate.trace_versions`
- `services.cli.meal_demo` JSON output
- `services.cli.meal_demo` `result_explanation`
- `meal_estimate_json` stored in SQLite
- JSON backup exports from `export_ledger_backup()`

## Verification

- `pytest tests/trace/test_version_metadata.py`
- `pytest tests/`
- `ruff check services tests`
