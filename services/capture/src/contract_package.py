from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import Field

from services.api import AnalyzePhotoFacadeRequest, AnalyzePhotoFacadeResponse, analyze_photo_facade
from services.capture import (
    DeviceCaptureMetadata,
    PhotoAnalyzeRequest,
    PhotoAnalyzeResponse,
    build_sanitized_capture_trace_artifact,
    resolve_scale_evidence_from_capture,
)
from services.capture.src.schemas import ImageIdentity, StrictModel


class CaptureQualitySummary(StrictModel):
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
    lens_hint: str | None = None


class CaptureTraceArtifact(StrictModel):
    image_identity: ImageIdentity
    capture_quality_summary: CaptureQualitySummary
    scale_evidence_ids: list[str] = Field(default_factory=list)
    barcode_detected: bool
    barcode_value_stored: bool
    barcode_value: str | None = None
    ocr_detected: bool
    ocr_text_stored: bool
    model_version: str | None = None
    prompt_version: str | None = None


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            payload,
            indent=2,
            sort_keys=True,
            default=lambda value: value.isoformat() if isinstance(value, datetime) else str(value),
        )
        + "\n",
        encoding="utf-8",
    )


def photo_analyze_response_from_facade(
    response: AnalyzePhotoFacadeResponse,
) -> PhotoAnalyzeResponse:
    """Map the canonical backend facade response into the iOS handoff shape."""
    return PhotoAnalyzeResponse(
        request_id=response.request_id,
        decision=response.status,
        reasons=list(response.reasons),
        metrics=(
            response.nutrition.model_dump(mode="json")
            if response.nutrition is not None
            else None
        ),
    )


def export_contract_package(base_dir: Path | None = None) -> None:
    root = base_dir or Path(__file__).resolve().parents[1] / "contracts"
    schemas_dir = root / "schemas"
    examples_dir = root / "examples"

    _write_json(
        schemas_dir / "photo_analyze_request.schema.json", PhotoAnalyzeRequest.model_json_schema()
    )
    _write_json(
        schemas_dir / "photo_analyze_response.schema.json",
        PhotoAnalyzeResponse.model_json_schema(),
    )
    _write_json(
        schemas_dir / "capture_metadata.schema.json", DeviceCaptureMetadata.model_json_schema()
    )
    _write_json(
        schemas_dir / "capture_trace_artifact.schema.json", CaptureTraceArtifact.model_json_schema()
    )

    top_down_depth_request = {
        "request_id": "req_accept_top_down_depth",
        "user_id": "user_demo_contract",
        "image_identity": {
            "image_sha256": "a" * 64,
            "image_format": "heic",
            "width_px": 3024,
            "height_px": 4032,
            "byte_size": 2456789,
        },
        "capture_metadata": {
            "device_model": "iPhone15,3",
            "os_version": "iOS 18.1",
            "camera_position": "back",
            "orientation": "portrait",
            "pitch_degrees": 1.2,
            "roll_degrees": -0.4,
            "focal_length_mm": 5.7,
            "lens_hint": "wide",
            "depth_available": True,
            "depth_quality": "high",
            "lidar_available": True,
            "arkit_scene_depth_supported": True,
            "arkit_smoothed_scene_depth_supported": True,
            "arkit_depth_available": True,
            "arkit_depth_quality": "high",
            "arkit_depth_map_width_px": 256,
            "arkit_depth_map_height_px": 192,
            "arkit_confidence_coverage": 0.86,
            "camera_intrinsics_available": True,
            "barcode_payload": None,
            "barcode_payload_safe": False,
            "ocr_text_snippets": ["brown rice", "grilled salmon"],
            "reference_object_hint": "standard dinner plate",
            "capture_timestamp": "2026-05-01T12:34:56+00:00",
        },
    }

    side_angle_weak_request = {
        "request_id": "req_warn_side_angle_weak",
        "user_id": "user_demo_contract",
        "image_identity": {
            "image_sha256": "b" * 64,
            "image_format": "jpeg",
            "width_px": 3024,
            "height_px": 4032,
            "byte_size": 1987001,
        },
        "capture_metadata": {
            "device_model": "iPhone14,5",
            "os_version": "iOS 17.7",
            "camera_position": "back",
            "orientation": "portrait",
            "pitch_degrees": 28.6,
            "roll_degrees": -12.1,
            "focal_length_mm": 5.7,
            "lens_hint": "wide",
            "depth_available": False,
            "depth_quality": "none",
            "lidar_available": False,
            "arkit_scene_depth_supported": False,
            "arkit_smoothed_scene_depth_supported": False,
            "arkit_depth_available": False,
            "arkit_depth_quality": "none",
            "arkit_depth_map_width_px": None,
            "arkit_depth_map_height_px": None,
            "arkit_confidence_coverage": None,
            "camera_intrinsics_available": False,
            "barcode_payload": None,
            "barcode_payload_safe": False,
            "ocr_text_snippets": [],
            "reference_object_hint": None,
            "capture_timestamp": "2026-05-01T12:37:03+00:00",
        },
    }

    barcode_packaged_request = {
        "request_id": "req_accept_barcode_packaged",
        "user_id": "user_demo_contract",
        "image_identity": {
            "image_sha256": "c" * 64,
            "image_format": "jpg",
            "width_px": 3024,
            "height_px": 4032,
            "byte_size": 1530440,
        },
        "capture_metadata": {
            "device_model": "iPhone15,2",
            "os_version": "iOS 18.0",
            "camera_position": "back",
            "orientation": "portrait",
            "pitch_degrees": 4.0,
            "roll_degrees": 1.5,
            "focal_length_mm": 5.7,
            "lens_hint": "wide",
            "depth_available": False,
            "depth_quality": "low",
            "lidar_available": False,
            "arkit_scene_depth_supported": False,
            "arkit_smoothed_scene_depth_supported": False,
            "arkit_depth_available": False,
            "arkit_depth_quality": "none",
            "arkit_depth_map_width_px": None,
            "arkit_depth_map_height_px": None,
            "arkit_confidence_coverage": None,
            "camera_intrinsics_available": False,
            "barcode_payload": "049000042511",
            "barcode_payload_safe": True,
            "ocr_text_snippets": ["Nutrition Facts", "Serving size 55g"],
            "reference_object_hint": "packaged_food_label",
            "capture_timestamp": "2026-05-01T12:40:12+00:00",
        },
    }

    missing_scale_clarify_request = {
        "request_id": "req_clarify_missing_scale",
        "user_id": "user_demo_contract",
        "image_identity": {
            "image_sha256": "d" * 64,
            "image_format": "heic",
            "width_px": 3024,
            "height_px": 4032,
            "byte_size": 2217990,
        },
        "capture_metadata": {
            "device_model": "iPhone13,4",
            "os_version": "iOS 17.6",
            "camera_position": "back",
            "orientation": "portrait",
            "pitch_degrees": 33.9,
            "roll_degrees": 17.2,
            "focal_length_mm": 5.7,
            "lens_hint": "wide",
            "depth_available": False,
            "depth_quality": "none",
            "lidar_available": False,
            "arkit_scene_depth_supported": False,
            "arkit_smoothed_scene_depth_supported": False,
            "arkit_depth_available": False,
            "arkit_depth_quality": "none",
            "arkit_depth_map_width_px": None,
            "arkit_depth_map_height_px": None,
            "arkit_confidence_coverage": None,
            "camera_intrinsics_available": False,
            "barcode_payload": None,
            "barcode_payload_safe": False,
            "ocr_text_snippets": [],
            "reference_object_hint": None,
            "capture_timestamp": "2026-05-01T12:44:48+00:00",
        },
    }

    def facade_response(photo_analyze_request: dict[str, Any]) -> dict[str, Any]:
        facade_request = AnalyzePhotoFacadeRequest.model_validate(photo_analyze_request)
        facade_payload = analyze_photo_facade(facade_request)
        return facade_payload.model_dump(mode="json")

    def handoff_response(photo_analyze_request: dict[str, Any]) -> dict[str, Any]:
        facade_payload = AnalyzePhotoFacadeResponse.model_validate(
            facade_response(photo_analyze_request)
        )
        return photo_analyze_response_from_facade(facade_payload).model_dump(mode="json")

    def artifact_scale_evidence_ids(photo_analyze_request: dict[str, Any]) -> list[str]:
        request_model = PhotoAnalyzeRequest.model_validate(photo_analyze_request)
        scale_evidence = resolve_scale_evidence_from_capture(
            trace_id=f"trace:{request_model.request_id}",
            capture_metadata=request_model.capture_metadata,
        )
        artifact = build_sanitized_capture_trace_artifact(
            request=request_model,
            scale_evidence=scale_evidence,
            model_version="vision_model_placeholder",
            prompt_version="vision_prompt_placeholder",
        )
        return list(artifact["scale_evidence_ids"])

    capture_trace_artifact = {
        "image_identity": top_down_depth_request["image_identity"],
        "capture_quality_summary": {
            "depth_available": True,
            "depth_quality": "high",
            "lidar_available": True,
            "arkit_scene_depth_supported": True,
            "arkit_smoothed_scene_depth_supported": True,
            "arkit_depth_available": True,
            "arkit_depth_quality": "high",
            "arkit_depth_map_width_px": 256,
            "arkit_depth_map_height_px": 192,
            "arkit_confidence_coverage": 0.86,
            "camera_intrinsics_available": True,
            "camera_position": "back",
            "orientation": "portrait",
            "pitch_degrees": 1.2,
            "roll_degrees": -0.4,
            "lens_hint": "wide",
        },
        "scale_evidence_ids": artifact_scale_evidence_ids(top_down_depth_request),
        "barcode_detected": False,
        "barcode_value_stored": False,
        "ocr_detected": True,
        "ocr_text_stored": False,
        "model_version": "vision_model_placeholder",
        "prompt_version": "vision_prompt_placeholder",
    }

    examples = {
        "top_down_photo_with_depth": {
            "photo_analyze_request": top_down_depth_request,
            "photo_analyze_response": handoff_response(top_down_depth_request),
            "analyze_photo_facade_response": facade_response(top_down_depth_request),
            "capture_trace_artifact": capture_trace_artifact,
        },
        "weak_side_angle_without_reference": {
            "photo_analyze_request": side_angle_weak_request,
            "photo_analyze_response": handoff_response(side_angle_weak_request),
            "analyze_photo_facade_response": facade_response(side_angle_weak_request),
            "capture_trace_artifact": {
                **capture_trace_artifact,
                "image_identity": side_angle_weak_request["image_identity"],
                "capture_quality_summary": {
                    "depth_available": False,
                    "depth_quality": "none",
                    "lidar_available": False,
                    "camera_position": "back",
                    "orientation": "portrait",
                    "pitch_degrees": 28.6,
                    "roll_degrees": -12.1,
                    "lens_hint": "wide",
                },
                "scale_evidence_ids": artifact_scale_evidence_ids(side_angle_weak_request),
                "ocr_detected": False,
            },
        },
        "barcode_packaged_food": {
            "photo_analyze_request": barcode_packaged_request,
            "photo_analyze_response": handoff_response(barcode_packaged_request),
            "analyze_photo_facade_response": facade_response(barcode_packaged_request),
            "capture_trace_artifact": {
                **capture_trace_artifact,
                "image_identity": barcode_packaged_request["image_identity"],
                "capture_quality_summary": {
                    "depth_available": False,
                    "depth_quality": "low",
                    "lidar_available": False,
                    "camera_position": "back",
                    "orientation": "portrait",
                    "pitch_degrees": 4.0,
                    "roll_degrees": 1.5,
                    "lens_hint": "wide",
                },
                "scale_evidence_ids": artifact_scale_evidence_ids(barcode_packaged_request),
                "barcode_detected": True,
                "barcode_value_stored": True,
                "barcode_value": "049000042511",
            },
        },
        "missing_scale_clarify_case": {
            "photo_analyze_request": missing_scale_clarify_request,
            "photo_analyze_response": handoff_response(missing_scale_clarify_request),
            "analyze_photo_facade_response": facade_response(missing_scale_clarify_request),
            "capture_trace_artifact": {
                **capture_trace_artifact,
                "image_identity": missing_scale_clarify_request["image_identity"],
                "capture_quality_summary": {
                    "depth_available": False,
                    "depth_quality": "none",
                    "lidar_available": False,
                    "camera_position": "back",
                    "orientation": "portrait",
                    "pitch_degrees": 33.9,
                    "roll_degrees": 17.2,
                    "lens_hint": "wide",
                },
                "scale_evidence_ids": [],
                "ocr_detected": False,
            },
        },
    }

    for name, payload in examples.items():
        PhotoAnalyzeRequest.model_validate(payload["photo_analyze_request"])
        PhotoAnalyzeResponse.model_validate(payload["photo_analyze_response"])
        AnalyzePhotoFacadeResponse.model_validate(payload["analyze_photo_facade_response"])
        CaptureTraceArtifact.model_validate(payload["capture_trace_artifact"])
        _write_json(examples_dir / f"{name}.json", payload)


if __name__ == "__main__":
    export_contract_package()
