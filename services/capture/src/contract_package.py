from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import Field

from services.api import AnalyzePhotoFacadeRequest, AnalyzePhotoFacadeResponse, analyze_photo_facade
from services.capture import DeviceCaptureMetadata, PhotoAnalyzeRequest, PhotoAnalyzeResponse
from services.capture.src.schemas import ImageIdentity, StrictModel


class CaptureQualitySummary(StrictModel):
    depth_available: bool
    depth_quality: Literal["none", "low", "medium", "high", "unknown"]
    lidar_available: bool
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

    capture_trace_artifact = {
        "image_identity": top_down_depth_request["image_identity"],
        "capture_quality_summary": {
            "depth_available": True,
            "depth_quality": "high",
            "lidar_available": True,
            "camera_position": "back",
            "orientation": "portrait",
            "pitch_degrees": 1.2,
            "roll_degrees": -0.4,
            "lens_hint": "wide",
        },
        "scale_evidence_ids": ["scale:lidar_depth:1", "scale:reference_object:1"],
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
            "photo_analyze_response": {
                "request_id": top_down_depth_request["request_id"],
                "decision": "ACCEPT",
                "reasons": ["adequate scale cues and stable camera pose"],
                "metrics": {
                    "kcal": {
                        "best_estimate": 520.0,
                        "min_estimate": 470.0,
                        "max_estimate": 590.0,
                        "source": "fdc:fixture",
                    },
                    "protein_g": {
                        "best_estimate": 35.0,
                        "min_estimate": 31.0,
                        "max_estimate": 40.0,
                        "source": "fdc:fixture",
                    },
                    "carbs_g": {
                        "best_estimate": 48.0,
                        "min_estimate": 42.0,
                        "max_estimate": 55.0,
                        "source": "fdc:fixture",
                    },
                    "fat_g": {
                        "best_estimate": 18.0,
                        "min_estimate": 15.0,
                        "max_estimate": 22.0,
                        "source": "fdc:fixture",
                    },
                    "sugar_g": {
                        "best_estimate": 8.0,
                        "min_estimate": 5.0,
                        "max_estimate": 11.0,
                        "source": "fdc:fixture",
                    },
                    "sodium_mg": {
                        "best_estimate": 640.0,
                        "min_estimate": 560.0,
                        "max_estimate": 730.0,
                        "source": "fdc:fixture",
                    },
                    "fiber_g": {
                        "best_estimate": 7.0,
                        "min_estimate": 5.0,
                        "max_estimate": 10.0,
                        "source": "fdc:fixture",
                    },
                },
            },
            "analyze_photo_facade_response": facade_response(top_down_depth_request),
            "capture_trace_artifact": capture_trace_artifact,
        },
        "weak_side_angle_without_reference": {
            "photo_analyze_request": side_angle_weak_request,
            "photo_analyze_response": {
                "request_id": side_angle_weak_request["request_id"],
                "decision": "WARN",
                "reasons": ["side-angle pose and no reference object increase uncertainty"],
                "metrics": {
                    "kcal": {
                        "best_estimate": 520.0,
                        "min_estimate": 430.0,
                        "max_estimate": 650.0,
                        "source": "fdc:fixture",
                    },
                    "protein_g": {
                        "best_estimate": 35.0,
                        "min_estimate": 28.0,
                        "max_estimate": 43.0,
                        "source": "fdc:fixture",
                    },
                    "carbs_g": {
                        "best_estimate": 48.0,
                        "min_estimate": 39.0,
                        "max_estimate": 61.0,
                        "source": "fdc:fixture",
                    },
                    "fat_g": {
                        "best_estimate": 18.0,
                        "min_estimate": 14.0,
                        "max_estimate": 23.0,
                        "source": "fdc:fixture",
                    },
                    "sugar_g": {
                        "best_estimate": 8.0,
                        "min_estimate": 4.0,
                        "max_estimate": 12.0,
                        "source": "fdc:fixture",
                    },
                    "sodium_mg": {
                        "best_estimate": 640.0,
                        "min_estimate": 510.0,
                        "max_estimate": 820.0,
                        "source": "fdc:fixture",
                    },
                    "fiber_g": {
                        "best_estimate": 7.0,
                        "min_estimate": 4.0,
                        "max_estimate": 11.0,
                        "source": "fdc:fixture",
                    },
                },
            },
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
                "scale_evidence_ids": ["scale:shape_prior:1"],
                "ocr_detected": False,
            },
        },
        "barcode_packaged_food": {
            "photo_analyze_request": barcode_packaged_request,
            "photo_analyze_response": {
                "request_id": barcode_packaged_request["request_id"],
                "decision": "ACCEPT",
                "reasons": ["barcode payload detected and accepted as safe"],
                "metrics": {
                    "kcal": {
                        "best_estimate": 240.0,
                        "min_estimate": 220.0,
                        "max_estimate": 265.0,
                        "source": "barcode_lookup",
                    },
                    "protein_g": {
                        "best_estimate": 4.0,
                        "min_estimate": 3.0,
                        "max_estimate": 5.0,
                        "source": "barcode_lookup",
                    },
                    "carbs_g": {
                        "best_estimate": 31.0,
                        "min_estimate": 28.0,
                        "max_estimate": 35.0,
                        "source": "barcode_lookup",
                    },
                    "fat_g": {
                        "best_estimate": 11.0,
                        "min_estimate": 10.0,
                        "max_estimate": 13.0,
                        "source": "barcode_lookup",
                    },
                    "sugar_g": {
                        "best_estimate": 13.0,
                        "min_estimate": 11.0,
                        "max_estimate": 15.0,
                        "source": "barcode_lookup",
                    },
                    "sodium_mg": {
                        "best_estimate": 210.0,
                        "min_estimate": 180.0,
                        "max_estimate": 250.0,
                        "source": "barcode_lookup",
                    },
                    "fiber_g": {
                        "best_estimate": 2.0,
                        "min_estimate": 1.0,
                        "max_estimate": 3.0,
                        "source": "barcode_lookup",
                    },
                },
            },
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
                "scale_evidence_ids": ["scale:barcode:1"],
                "barcode_detected": True,
                "barcode_value_stored": True,
                "barcode_value": "049000042511",
            },
        },
        "missing_scale_clarify_case": {
            "photo_analyze_request": missing_scale_clarify_request,
            "photo_analyze_response": {
                "request_id": missing_scale_clarify_request["request_id"],
                "decision": "CLARIFY",
                "reasons": ["missing scale evidence; clarify required before logging"],
                "metrics": None,
            },
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
