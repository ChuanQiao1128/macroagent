from __future__ import annotations

import base64
import hashlib
import json
import os
import subprocess
import tempfile
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any, Literal

from PIL import Image, ImageOps
from pydantic import AliasChoices, BaseModel, ConfigDict, Field, ValidationError

from services.nutrition.src.version_metadata import (
    VISION_MODEL_NAME,
    VISION_PROMPT_TEXT,
    VISION_SCHEMA_VERSION,
    TraceVersionMetadata,
    build_trace_version_metadata,
)
from services.vision.src.cache import VisionResultCache

DEFAULT_MODEL = VISION_MODEL_NAME
DEFAULT_CLAUDE_CLI_MODEL = "sonnet"
DEFAULT_PROMPT = VISION_PROMPT_TEXT
TOOL_NAME = "extract_food_components"
STRUCTURED_CACHE_FORMAT = VISION_SCHEMA_VERSION
VISION_PROVIDER_ENV = "VISION_PROVIDER"
VISION_PROVIDER_CLAUDE_CLI = "claude_cli"
VISION_PROVIDER_ANTHROPIC = "anthropic"


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


class ClaudeCliVisionClient:
    """Analyze meal photos through Claude Code subscription auth instead of API keys."""

    def __init__(
        self,
        *,
        model: str | None = None,
        max_long_side: int = 1024,
        cache: VisionResultCache | None = None,
        claude_binary: str = "claude",
        timeout_seconds: int = 180,
        cwd: str | Path | None = None,
    ) -> None:
        self.model = model or os.getenv("CLAUDE_CLI_MODEL", DEFAULT_CLAUDE_CLI_MODEL)
        self.max_long_side = max_long_side
        self._cache = cache
        self.claude_binary = claude_binary
        self.timeout_seconds = timeout_seconds
        self.cwd = Path(cwd) if cwd is not None else Path.cwd()

    def analyze_meal_photo(
        self,
        image: str | Path | bytes | bytearray,
        *,
        prompt: str = DEFAULT_PROMPT,
    ) -> list[FoodComponent]:
        return self.analyze_meal_photo_structured(image, prompt=prompt).to_food_components()

    def analyze_meal_photo_structured(
        self,
        image: str | Path | bytes | bytearray,
        *,
        prompt: str = DEFAULT_PROMPT,
    ) -> VisionAnalysisResponse:
        prepared = self._prepare_image(image)
        image_hash = ClaudeVisionClient._image_hash(prepared.data)
        cache_key = ClaudeVisionClient._cache_key(
            image_hash=image_hash,
            model=self.model,
            prompt=prompt,
        )
        structured_cache_key = ClaudeVisionClient._structured_cache_key(
            image_hash=image_hash,
            model=self.model,
            prompt=prompt,
        )

        if self._cache is not None:
            cached_structured = ClaudeVisionClient._deserialize_structured_cache_payload(
                self._cache.get(structured_cache_key)
            )
            if cached_structured is not None:
                return self._with_trace_versions(cached_structured, prompt=prompt)
            cached_components = self._cache.get(cache_key)
            if cached_components is not None:
                legacy = FoodComponentsResponse.model_validate(
                    {"components": cached_components}
                )
                return self._with_trace_versions(
                    ClaudeVisionClient._legacy_components_to_structured(legacy.components),
                    prompt=prompt,
                )

        structured = self._with_trace_versions(
            self._analyze_meal_photo_structured(prepared=prepared, prompt=prompt),
            prompt=prompt,
        )

        if self._cache is not None:
            self._cache.set(
                structured_cache_key,
                ClaudeVisionClient._serialize_structured_cache_payload(structured),
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
                    vision_model_name=f"claude-cli:{self.model}",
                    vision_prompt_text=prompt,
                )
            }
        )

    def _prepare_image(self, image: str | Path | bytes | bytearray) -> PreparedImage:
        raw = ClaudeVisionClient._read_image_bytes(image)
        ClaudeVisionClient._register_heif_opener()

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

    def _analyze_meal_photo_structured(
        self,
        *,
        prepared: PreparedImage,
        prompt: str,
    ) -> VisionAnalysisResponse:
        last_error: Exception | None = None

        with tempfile.TemporaryDirectory(prefix="macroagent_vision_") as tmp_dir:
            prepared_path = Path(tmp_dir) / "prepared_meal.jpg"
            prepared_path.write_bytes(prepared.data)

            for attempt in range(2):
                try:
                    return self._run_claude_cli(
                        image_path=prepared_path,
                        prompt=ClaudeVisionClient._prompt_for_attempt(prompt, attempt),
                        add_dir=Path(tmp_dir),
                    )
                except (ValidationError, VisionParseError, TypeError, ValueError) as exc:
                    last_error = exc

        raise VisionParseError(
            "Claude CLI vision response did not match VisionAnalysisResponse schema"
        ) from last_error

    def _run_claude_cli(
        self,
        *,
        image_path: Path,
        prompt: str,
        add_dir: Path,
    ) -> VisionAnalysisResponse:
        env = dict(os.environ)
        env.pop("ANTHROPIC_API_KEY", None)
        command = [
            self.claude_binary,
            "-p",
            "--model",
            self.model,
            "--permission-mode",
            "dontAsk",
            "--output-format",
            "json",
            "--json-schema",
            json.dumps(_claude_cli_vision_schema(), separators=(",", ":")),
            "--add-dir",
            str(add_dir),
            (
                f"Analyze @{image_path} as a meal photo.\n\n"
                f"{prompt}\n\n"
                "Return only the structured output fields required by the JSON schema."
            ),
        ]
        completed = subprocess.run(
            command,
            cwd=self.cwd,
            env=env,
            capture_output=True,
            text=True,
            timeout=self.timeout_seconds,
            check=False,
        )
        if completed.returncode != 0:
            message = (completed.stderr or completed.stdout).strip()
            raise VisionParseError(f"Claude CLI failed: {message}")

        output = json.loads(completed.stdout)
        if output.get("is_error") is True:
            raise VisionParseError(f"Claude CLI returned an error: {output.get('result')}")

        payload = output.get("structured_output")
        if payload is None and isinstance(output.get("result"), str):
            payload = json.loads(output["result"])
        if payload is None:
            raise VisionParseError("Claude CLI output did not include structured_output")

        return ClaudeVisionClient._validate_structured_payload(payload)


def _claude_cli_vision_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "image_quality_issues": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "issue": {"type": "string"},
                        "severity": {"type": "string", "enum": ["low", "medium", "high"]},
                        "impact": {"type": ["string", "null"]},
                    },
                    "required": ["issue", "severity"],
                    "additionalProperties": False,
                },
            },
            "meal_uncertainty_flags": {"type": "array", "items": {"type": "string"}},
            "components": {
                "type": "array",
                "minItems": 1,
                "items": {
                    "type": "object",
                    "properties": {
                        "component_id": {"type": "string"},
                        "visible_name": {"type": "string"},
                        "candidates": {
                            "type": "array",
                            "minItems": 1,
                            "maxItems": 5,
                            "items": {
                                "type": "object",
                                "properties": {
                                    "name": {"type": "string"},
                                    "confidence": {
                                        "type": "number",
                                        "minimum": 0,
                                        "maximum": 1,
                                    },
                                    "visual_evidence": {
                                        "type": "array",
                                        "minItems": 1,
                                        "items": {"type": "string"},
                                    },
                                },
                                "required": ["name", "confidence", "visual_evidence"],
                                "additionalProperties": False,
                            },
                        },
                        "portion": {
                            "type": "object",
                            "properties": {
                                "description": {"type": "string"},
                                "confidence": {
                                    "type": "number",
                                    "minimum": 0,
                                    "maximum": 1,
                                },
                                "visual_basis": {
                                    "type": "array",
                                    "minItems": 1,
                                    "items": {"type": "string"},
                                },
                            },
                            "required": ["description", "confidence", "visual_basis"],
                            "additionalProperties": False,
                        },
                        "state_hints": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "state": {
                                        "type": "string",
                                        "enum": [
                                            "cooked",
                                            "raw",
                                            "fried",
                                            "grilled",
                                            "boiled",
                                            "plain",
                                            "sauced",
                                        ],
                                    },
                                    "confidence": {
                                        "type": "number",
                                        "minimum": 0,
                                        "maximum": 1,
                                    },
                                    "visual_evidence": {
                                        "type": "array",
                                        "items": {"type": "string"},
                                    },
                                },
                                "required": ["state", "confidence", "visual_evidence"],
                                "additionalProperties": False,
                            },
                        },
                        "hidden_ingredient_risks": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "ingredient": {"type": "string"},
                                    "likelihood": {
                                        "type": "number",
                                        "minimum": 0,
                                        "maximum": 1,
                                    },
                                    "macro_impact": {
                                        "type": "string",
                                        "enum": ["low", "medium", "high", "unknown"],
                                    },
                                    "rationale": {"type": ["string", "null"]},
                                },
                                "required": ["ingredient", "likelihood", "macro_impact"],
                                "additionalProperties": False,
                            },
                        },
                    },
                    "required": [
                        "component_id",
                        "visible_name",
                        "candidates",
                        "portion",
                        "state_hints",
                        "hidden_ingredient_risks",
                    ],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["image_quality_issues", "meal_uncertainty_flags", "components"],
        "additionalProperties": False,
    }


def _selected_vision_provider(client: Any | None) -> str:
    if client is not None:
        return VISION_PROVIDER_ANTHROPIC
    provider = os.getenv(VISION_PROVIDER_ENV, VISION_PROVIDER_CLAUDE_CLI)
    normalized = provider.strip().casefold().replace("-", "_")
    if normalized in {"claude", "claude_cli", "claude_code", "subscription"}:
        return VISION_PROVIDER_CLAUDE_CLI
    if normalized in {"anthropic", "api", "anthropic_api"}:
        return VISION_PROVIDER_ANTHROPIC
    raise ValueError(
        f"unsupported {VISION_PROVIDER_ENV}={provider!r}; "
        "use 'claude_cli' or 'anthropic'"
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
    if _selected_vision_provider(client) == VISION_PROVIDER_CLAUDE_CLI:
        return ClaudeCliVisionClient(model=model, cache=cache).analyze_meal_photo(image)
    return ClaudeVisionClient(client=client, model=model, cache=cache).analyze_meal_photo(image)


def analyze_meal_photo_structured(
    image: str | Path | bytes | bytearray,
    *,
    client: Any | None = None,
    model: str | None = None,
    cache: VisionResultCache | None = None,
) -> VisionAnalysisResponse:
    if _selected_vision_provider(client) == VISION_PROVIDER_CLAUDE_CLI:
        return ClaudeCliVisionClient(model=model, cache=cache).analyze_meal_photo_structured(
            image
        )
    vision_client = ClaudeVisionClient(client=client, model=model, cache=cache)
    return vision_client.analyze_meal_photo_structured(image)
