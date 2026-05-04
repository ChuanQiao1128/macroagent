from __future__ import annotations

import base64
import hashlib
import json
import os
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any, Literal

from PIL import Image, ImageOps
from pydantic import AliasChoices, BaseModel, ConfigDict, Field, ValidationError

from services.trace import (
    VISION_MODEL_NAME,
    VISION_PROMPT_TEXT,
    VISION_SCHEMA_VERSION,
    TraceVersionMetadata,
    build_trace_version_metadata,
)
from services.vision.src.cache import VisionResultCache

DEFAULT_MODEL = VISION_MODEL_NAME
DEFAULT_PROMPT = VISION_PROMPT_TEXT
TOOL_NAME = "extract_food_components"
STRUCTURED_CACHE_FORMAT = VISION_SCHEMA_VERSION


class VisionParseError(ValueError):
    """Raised when Claude returns content that does not match the expected schema."""


class FoodComponent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1)
    confidence: float = Field(..., ge=0.0, le=1.0)
    portion_hint: str | None = None


class FoodComponentsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    components: list[FoodComponent]


class ImageQualityIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    issue: str = Field(
        ...,
        min_length=1,
        validation_alias=AliasChoices("issue", "usability_issue", "description"),
    )
    severity: Literal["low", "medium", "high"]
    impact: str | None = None


class FoodCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1, validation_alias=AliasChoices("name", "food_name"))
    confidence: float = Field(..., ge=0.0, le=1.0)
    visual_evidence: list[str] = Field(
        ...,
        min_length=1,
        validation_alias=AliasChoices("visual_evidence", "evidence"),
    )


class PortionEstimate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    description: str = Field(
        ...,
        min_length=1,
        validation_alias=AliasChoices("description", "portion_description"),
    )
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        validation_alias=AliasChoices("confidence", "portion_confidence"),
    )
    visual_basis: list[str] = Field(
        ...,
        min_length=1,
        validation_alias=AliasChoices("visual_basis", "visual_evidence"),
    )


class StateHint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state: Literal["cooked", "raw", "fried", "grilled", "boiled", "plain", "sauced"]
    confidence: float = Field(..., ge=0.0, le=1.0)
    visual_evidence: list[str] = Field(default_factory=list)


class HiddenIngredientRisk(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ingredient: str = Field(..., min_length=1)
    likelihood: float = Field(..., ge=0.0, le=1.0)
    macro_impact: Literal["low", "medium", "high", "unknown"]
    rationale: str | None = None


class StructuredFoodComponent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    component_id: str = Field(
        ...,
        min_length=1,
        validation_alias=AliasChoices("component_id", "id"),
    )
    visible_name: str = Field(
        ...,
        min_length=1,
        validation_alias=AliasChoices("visible_name", "name"),
    )
    candidates: list[FoodCandidate] = Field(
        ...,
        min_length=1,
        max_length=5,
        validation_alias=AliasChoices("candidates", "top_candidates", "top_k_candidates"),
    )
    portion: PortionEstimate = Field(
        ...,
        validation_alias=AliasChoices("portion", "portion_estimate"),
    )
    state_hints: list[StateHint] = Field(
        default_factory=list,
        validation_alias=AliasChoices("state_hints", "state"),
    )
    hidden_ingredient_risks: list[HiddenIngredientRisk] = Field(
        default_factory=list,
        validation_alias=AliasChoices("hidden_ingredient_risks", "hidden_risks"),
    )


class VisionAnalysisResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    image_quality_issues: list[ImageQualityIssue] = Field(default_factory=list)
    meal_uncertainty_flags: list[str] = Field(
        default_factory=list,
        validation_alias=AliasChoices("meal_uncertainty_flags", "uncertainty_flags"),
    )
    components: list[StructuredFoodComponent]
    trace_versions: TraceVersionMetadata = Field(default_factory=build_trace_version_metadata)

    def to_food_components(self) -> list[FoodComponent]:
        results: list[FoodComponent] = []
        for component in self.components:
            top_candidate = component.candidates[0]
            results.append(
                FoodComponent(
                    name=top_candidate.name,
                    confidence=top_candidate.confidence,
                    portion_hint=component.portion.description,
                )
            )
        return results


@dataclass(frozen=True)
class PreparedImage:
    media_type: str
    data: bytes


class ClaudeVisionClient:
    def __init__(
        self,
        *,
        client: Any | None = None,
        model: str | None = None,
        max_long_side: int = 1024,
        cache: VisionResultCache | None = None,
    ) -> None:
        self.model = model or os.getenv("ANTHROPIC_MODEL", DEFAULT_MODEL)
        self.max_long_side = max_long_side
        self._client = client or self._build_default_client()
        self._cache = cache

    def analyze_meal_photo(
        self,
        image: str | Path | bytes | bytearray,
        *,
        prompt: str = DEFAULT_PROMPT,
    ) -> list[FoodComponent]:
        prepared = self._prepare_image(image)
        image_hash = self._image_hash(prepared.data)
        cache_key = self._cache_key(image_hash=image_hash, model=self.model, prompt=prompt)
        structured_cache_key = self._structured_cache_key(
            image_hash=image_hash,
            model=self.model,
            prompt=prompt,
        )
        if self._cache is not None:
            cached_components = self._cache.get(cache_key)
            if cached_components is not None:
                return FoodComponentsResponse.model_validate(
                    {"components": cached_components}
                ).components
            cached_structured = self._deserialize_structured_cache_payload(
                self._cache.get(structured_cache_key)
            )
            if cached_structured is not None:
                return self._with_trace_versions(
                    cached_structured,
                    prompt=prompt,
                ).to_food_components()

        structured = self._with_trace_versions(
            self._analyze_meal_photo_structured(prepared=prepared, prompt=prompt),
            prompt=prompt,
        )
        components = structured.to_food_components()

        if self._cache is not None:
            self._cache.set(
                structured_cache_key,
                self._serialize_structured_cache_payload(structured),
            )
            self._cache.set(
                cache_key,
                [component.model_dump(mode="json") for component in components],
            )

        return components

    def analyze_meal_photo_structured(
        self,
        image: str | Path | bytes | bytearray,
        *,
        prompt: str = DEFAULT_PROMPT,
    ) -> VisionAnalysisResponse:
        prepared = self._prepare_image(image)
        image_hash = self._image_hash(prepared.data)
        cache_key = self._cache_key(image_hash=image_hash, model=self.model, prompt=prompt)
        structured_cache_key = self._structured_cache_key(
            image_hash=image_hash, model=self.model, prompt=prompt
        )

        if self._cache is not None:
            cached_structured = self._deserialize_structured_cache_payload(
                self._cache.get(structured_cache_key)
            )
            if cached_structured is not None:
                return self._with_trace_versions(cached_structured, prompt=prompt)

        structured = self._with_trace_versions(
            self._analyze_meal_photo_structured(prepared=prepared, prompt=prompt),
            prompt=prompt,
        )

        if self._cache is not None:
            self._cache.set(
                structured_cache_key,
                self._serialize_structured_cache_payload(structured),
            )
            self._cache.set(
                cache_key,
                [
                    component.model_dump(mode="json")
                    for component in structured.to_food_components()
                ],
            )

        return structured

    def _with_trace_versions(
        self,
        structured: VisionAnalysisResponse,
        *,
        prompt: str,
    ) -> VisionAnalysisResponse:
        return structured.model_copy(
            update={
                "trace_versions": build_trace_version_metadata(
                    vision_model_name=self.model,
                    vision_prompt_text=prompt,
                )
            }
        )

    @staticmethod
    def _build_default_client() -> Any:
        try:
            from anthropic import Anthropic
        except ImportError as exc:
            raise RuntimeError("Install the anthropic package to use ClaudeVisionClient") from exc
        return Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    @staticmethod
    def _tool_schema() -> dict[str, Any]:
        return {
            "name": TOOL_NAME,
            "description": "Return structured uncertainty-aware meal component observations.",
            "input_schema": VisionAnalysisResponse.model_json_schema(),
        }

    @staticmethod
    def _prompt_for_attempt(prompt: str, attempt: int) -> str:
        if attempt == 0:
            return prompt
        return (
            f"{prompt}\n\nThe previous response failed schema validation. "
            "Call the tool again with only valid schema fields and no nutrition totals or macros."
        )

    @staticmethod
    def _image_hash(normalized_jpeg_bytes: bytes) -> str:
        return hashlib.sha256(normalized_jpeg_bytes).hexdigest()

    @staticmethod
    def _cache_key(*, image_hash: str, model: str, prompt: str) -> str:
        return json.dumps(
            {
                "image_hash": image_hash,
                "model": model,
                "prompt": prompt,
            },
            sort_keys=True,
            separators=(",", ":"),
        )

    @staticmethod
    def _structured_cache_key(*, image_hash: str, model: str, prompt: str) -> str:
        return json.dumps(
            {
                "image_hash": image_hash,
                "model": model,
                "prompt": prompt,
                "response_format": STRUCTURED_CACHE_FORMAT,
            },
            sort_keys=True,
            separators=(",", ":"),
        )

    @staticmethod
    def _serialize_structured_cache_payload(
        structured: VisionAnalysisResponse,
    ) -> list[dict[str, Any]]:
        return [
            {
                "_cache_format": STRUCTURED_CACHE_FORMAT,
                "payload": structured.model_dump(mode="json"),
            }
        ]

    @staticmethod
    def _deserialize_structured_cache_payload(
        payload: list[dict[str, Any]] | None,
    ) -> VisionAnalysisResponse | None:
        if not isinstance(payload, list) or len(payload) != 1:
            return None
        record = payload[0]
        if not isinstance(record, dict):
            return None
        if record.get("_cache_format") != STRUCTURED_CACHE_FORMAT:
            return None
        try:
            return VisionAnalysisResponse.model_validate(record.get("payload"))
        except ValidationError:
            return None

    def _prepare_image(self, image: str | Path | bytes | bytearray) -> PreparedImage:
        raw = self._read_image_bytes(image)
        self._register_heif_opener()

        with Image.open(BytesIO(raw)) as opened:
            img = ImageOps.exif_transpose(opened)
            if img.mode not in {"RGB", "L"}:
                img = img.convert("RGB")
            elif img.mode == "L":
                img = img.convert("RGB")

            if max(img.size) > self.max_long_side:
                img.thumbnail((self.max_long_side, self.max_long_side), Image.Resampling.LANCZOS)

            out = BytesIO()
            img.save(out, format="JPEG", quality=90, optimize=True)
            return PreparedImage(media_type="image/jpeg", data=out.getvalue())

    @staticmethod
    def _read_image_bytes(image: str | Path | bytes | bytearray) -> bytes:
        if isinstance(image, bytes):
            return image
        if isinstance(image, bytearray):
            return bytes(image)
        return Path(image).read_bytes()

    @staticmethod
    def _register_heif_opener() -> None:
        try:
            from pillow_heif import register_heif_opener
        except ImportError:
            return
        register_heif_opener()

    def _analyze_meal_photo_structured(
        self,
        *,
        prepared: PreparedImage,
        prompt: str,
    ) -> VisionAnalysisResponse:
        encoded_image = base64.b64encode(prepared.data).decode("ascii")
        last_error: Exception | None = None

        for attempt in range(2):
            response = self._client.messages.create(
                model=self.model,
                max_tokens=1000,
                temperature=0,
                tools=[self._tool_schema()],
                tool_choice={"type": "tool", "name": TOOL_NAME},
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": prepared.media_type,
                                    "data": encoded_image,
                                },
                            },
                            {"type": "text", "text": self._prompt_for_attempt(prompt, attempt)},
                        ],
                    }
                ],
            )

            try:
                return self._parse_structured_response(response)
            except (ValidationError, VisionParseError, TypeError, ValueError) as exc:
                last_error = exc

        raise VisionParseError(
            "Claude vision response did not match VisionAnalysisResponse schema"
        ) from last_error

    @classmethod
    def _parse_structured_response(cls, response: Any) -> VisionAnalysisResponse:
        for block in getattr(response, "content", []) or []:
            block_type = _read_attr(block, "type")
            block_name = _read_attr(block, "name")
            if block_type == "tool_use" and block_name == TOOL_NAME:
                payload = _read_attr(block, "input")
                return cls._validate_structured_payload(payload)

        text = "".join(
            str(_read_attr(block, "text"))
            for block in getattr(response, "content", []) or []
            if _read_attr(block, "type") == "text" and _read_attr(block, "text") is not None
        ).strip()
        if text:
            payload = json.loads(text)
            if isinstance(payload, list):
                payload = {"components": payload}
            return cls._validate_structured_payload(payload)

        raise VisionParseError("Claude response did not include a matching tool call")

    @classmethod
    def _validate_structured_payload(cls, payload: Any) -> VisionAnalysisResponse:
        try:
            return VisionAnalysisResponse.model_validate(payload)
        except ValidationError:
            legacy = FoodComponentsResponse.model_validate(payload)
            return cls._legacy_components_to_structured(legacy.components)
        except TypeError:
            legacy = FoodComponentsResponse.model_validate({"components": payload})
            return cls._legacy_components_to_structured(legacy.components)

    @staticmethod
    def _legacy_components_to_structured(
        components: list[FoodComponent],
    ) -> VisionAnalysisResponse:
        structured_components: list[StructuredFoodComponent] = []
        for index, component in enumerate(components, start=1):
            portion_description = component.portion_hint or "unspecified portion"
            structured_components.append(
                StructuredFoodComponent(
                    component_id=f"component_{index}",
                    visible_name=component.name,
                    candidates=[
                        FoodCandidate(
                            name=component.name,
                            confidence=component.confidence,
                            visual_evidence=["legacy_simple_response_no_visual_evidence"],
                        )
                    ],
                    portion=PortionEstimate(
                        description=portion_description,
                        confidence=component.confidence,
                        visual_basis=["legacy_simple_response_no_visual_basis"],
                    ),
                    state_hints=[],
                    hidden_ingredient_risks=[],
                )
            )
        return VisionAnalysisResponse(
            image_quality_issues=[],
            meal_uncertainty_flags=["legacy_simple_response"],
            components=structured_components,
        )


def _read_attr(value: Any, name: str) -> Any:
    if isinstance(value, dict):
        return value.get(name)
    return getattr(value, name, None)


def analyze_meal_photo(
    image: str | Path | bytes | bytearray,
    *,
    client: Any | None = None,
    model: str | None = None,
    cache: VisionResultCache | None = None,
) -> list[FoodComponent]:
    return ClaudeVisionClient(client=client, model=model, cache=cache).analyze_meal_photo(image)


def analyze_meal_photo_structured(
    image: str | Path | bytes | bytearray,
    *,
    client: Any | None = None,
    model: str | None = None,
    cache: VisionResultCache | None = None,
) -> VisionAnalysisResponse:
    vision_client = ClaudeVisionClient(client=client, model=model, cache=cache)
    return vision_client.analyze_meal_photo_structured(image)
