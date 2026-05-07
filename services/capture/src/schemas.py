from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class ImageIdentity(StrictModel):
    image_sha256: str = Field(pattern=r"^[A-Fa-f0-9]{64}$")
    image_format: Literal["jpeg", "jpg", "heic", "heif", "png", "webp"]
    width_px: int = Field(gt=0)
    height_px: int = Field(gt=0)
    byte_size: int = Field(gt=0)


class DeviceCaptureMetadata(StrictModel):
    device_model: str = Field(min_length=1)
    os_version: str = Field(min_length=1)
    camera_position: Literal["front", "back", "unknown"]
    orientation: Literal[
        "portrait",
        "portrait_upside_down",
        "landscape_left",
        "landscape_right",
        "face_up",
        "face_down",
        "unknown",
    ]
    pitch_degrees: float = Field(ge=-180, le=180)
    roll_degrees: float = Field(ge=-180, le=180)
    focal_length_mm: float | None = Field(default=None, gt=0)
    lens_hint: str | None = None
    depth_available: bool
    depth_quality: Literal["none", "low", "medium", "high", "unknown"]
    lidar_available: bool
    arkit_scene_depth_supported: bool = False
    arkit_smoothed_scene_depth_supported: bool = False
    arkit_depth_available: bool = False
    arkit_depth_quality: Literal["none", "low", "medium", "high", "unknown"] = "none"
    arkit_depth_map_width_px: int | None = Field(default=None, gt=0)
    arkit_depth_map_height_px: int | None = Field(default=None, gt=0)
    arkit_confidence_coverage: float | None = Field(default=None, ge=0, le=1)
    camera_intrinsics_available: bool = False
    barcode_payload: str | None = None
    barcode_payload_safe: bool = False
    ocr_text_snippets: list[str] = Field(default_factory=list)
    reference_object_hint: str | None = None
    capture_timestamp: datetime


class PhotoAnalyzeRequest(StrictModel):
    request_id: str = Field(min_length=1)
    user_id: str = Field(min_length=1)
    image_identity: ImageIdentity
    capture_metadata: DeviceCaptureMetadata

    @model_validator(mode="before")
    @classmethod
    def _reject_raw_image_fields(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data

        forbidden_fields = {
            "image",
            "image_bytes",
            "raw_image",
            "raw_bytes",
            "base64_image",
            "image_base64",
            "file",
            "files",
            "file_handle",
            "local_image_path",
            "image_path",
            "path",
        }
        received = forbidden_fields.intersection(data.keys())
        if received:
            names = ", ".join(sorted(received))
            raise ValueError(
                f"raw image content is not allowed in request payload; remove fields: {names}"
            )

        metadata = data.get("capture_metadata")
        if isinstance(metadata, dict):
            capture_timestamp = metadata.get("capture_timestamp")
            if isinstance(capture_timestamp, str):
                metadata["capture_timestamp"] = datetime.fromisoformat(capture_timestamp)
            metadata_received = forbidden_fields.intersection(metadata.keys())
            if metadata_received:
                names = ", ".join(sorted(metadata_received))
                raise ValueError(
                    "raw image content is not allowed in capture metadata; "
                    f"remove fields: {names}"
                )

        return data


class NutritionMetric(StrictModel):
    best_estimate: float = Field(ge=0)
    min_estimate: float = Field(ge=0)
    max_estimate: float = Field(ge=0)
    source: str = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_range(self) -> NutritionMetric:
        if not self.min_estimate <= self.best_estimate <= self.max_estimate:
            raise ValueError(
                "nutrition metric must satisfy "
                "min_estimate <= best_estimate <= max_estimate"
            )
        return self


class NutritionMetrics(StrictModel):
    kcal: NutritionMetric
    protein_g: NutritionMetric
    carbs_g: NutritionMetric
    fat_g: NutritionMetric
    sugar_g: NutritionMetric
    sodium_mg: NutritionMetric
    fiber_g: NutritionMetric


class PhotoAnalyzeResponse(StrictModel):
    request_id: str = Field(min_length=1)
    decision: Literal["ACCEPT", "WARN", "CLARIFY", "BLOCK"]
    reasons: list[str] = Field(default_factory=list)
    metrics: NutritionMetrics | None = None

    @model_validator(mode="after")
    def _validate_metrics_requirement(self) -> PhotoAnalyzeResponse:
        if self.decision in {"ACCEPT", "WARN"} and self.metrics is None:
            raise ValueError("metrics are required when decision is ACCEPT or WARN")
        return self
