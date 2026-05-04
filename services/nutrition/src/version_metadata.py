from __future__ import annotations

import hashlib

from pydantic import BaseModel, ConfigDict, Field

VISION_SCHEMA_VERSION = "vision_analysis_response_v1"
VISION_MODEL_NAME = "claude-sonnet-4-5-20250929"
VISION_PROMPT_TEXT = (
    "Analyze this meal photo as uncertain visual evidence only. "
    "Return image-quality issues, meal uncertainty flags, and for each visible component include "
    "a component id, visible name, top food candidates with confidence and visual evidence, "
    "portion estimate with confidence and visual basis, visible state hints, and hidden ingredient "
    "risks with likelihood and macro impact. Do not provide kcal, protein, carbs, fat, "
    "or meal totals. "
    "Use the tool schema only."
)
NUTRITION_CATALOG_VERSION = "nutrition_catalog_seed_fdc_v2"
MATCHER_VERSION = "matcher_state_aware_fdc_v2"
PORTION_ENGINE_VERSION = "portion_parser_v1"
MACRO_CALCULATOR_VERSION = "macro_interval_v1"
LEDGER_SCHEMA_VERSION = 2


class TraceVersionMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    vision_schema_version: str = Field(..., min_length=1)
    vision_model_name: str = Field(..., min_length=1)
    vision_prompt_hash: str = Field(..., min_length=1)
    nutrition_catalog_version: str = Field(..., min_length=1)
    matcher_version: str = Field(..., min_length=1)
    portion_engine_version: str = Field(..., min_length=1)
    macro_calculator_version: str = Field(..., min_length=1)
    ledger_schema_version: int = Field(..., ge=1)


def prompt_sha256(prompt_text: str) -> str:
    return hashlib.sha256(prompt_text.encode("utf-8")).hexdigest()


def build_trace_version_metadata(
    *,
    vision_model_name: str = VISION_MODEL_NAME,
    vision_prompt_text: str = VISION_PROMPT_TEXT,
) -> TraceVersionMetadata:
    return TraceVersionMetadata(
        vision_schema_version=VISION_SCHEMA_VERSION,
        vision_model_name=vision_model_name,
        vision_prompt_hash=prompt_sha256(vision_prompt_text),
        nutrition_catalog_version=NUTRITION_CATALOG_VERSION,
        matcher_version=MATCHER_VERSION,
        portion_engine_version=PORTION_ENGINE_VERSION,
        macro_calculator_version=MACRO_CALCULATOR_VERSION,
        ledger_schema_version=LEDGER_SCHEMA_VERSION,
    )


DEFAULT_TRACE_VERSION_METADATA = build_trace_version_metadata()


__all__ = [
    "DEFAULT_TRACE_VERSION_METADATA",
    "LEDGER_SCHEMA_VERSION",
    "MACRO_CALCULATOR_VERSION",
    "MATCHER_VERSION",
    "NUTRITION_CATALOG_VERSION",
    "PORTION_ENGINE_VERSION",
    "TraceVersionMetadata",
    "VISION_MODEL_NAME",
    "VISION_PROMPT_TEXT",
    "VISION_SCHEMA_VERSION",
    "build_trace_version_metadata",
    "prompt_sha256",
]
