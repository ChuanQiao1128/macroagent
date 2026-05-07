from __future__ import annotations

import pytest
from pydantic import ValidationError

from services.capture import PhotoAnalyzeRequest, PhotoAnalyzeResponse


def _valid_request_payload() -> dict:
    return {
        "request_id": "req_123",
        "user_id": "user_abc",
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
            "pitch_degrees": 2.5,
            "roll_degrees": -1.0,
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
            "arkit_confidence_coverage": 0.84,
            "camera_intrinsics_available": True,
            "barcode_payload": "0123456789012",
            "ocr_text_snippets": ["2 tbsp olive oil", "chicken breast"],
            "reference_object_hint": "standard dinner plate",
            "capture_timestamp": "2026-05-01T12:34:56+00:00",
        },
    }


def _metric(value: float) -> dict:
    return {
        "best_estimate": value,
        "min_estimate": value - 1,
        "max_estimate": value + 1,
        "source": "estimator_v1",
    }


def test_photo_analyze_request_accepts_realistic_iphone_metadata() -> None:
    payload = _valid_request_payload()

    request = PhotoAnalyzeRequest.model_validate(payload)

    assert request.request_id == "req_123"
    assert request.image_identity.image_format == "heic"
    assert request.capture_metadata.device_model == "iPhone15,3"
    assert request.capture_metadata.capture_timestamp.isoformat() == "2026-05-01T12:34:56+00:00"


def test_photo_analyze_request_rejects_invalid_extra_fields() -> None:
    payload = _valid_request_payload()
    payload["extra_field"] = "nope"

    with pytest.raises(ValidationError):
        PhotoAnalyzeRequest.model_validate(payload)


@pytest.mark.parametrize(
    "forbidden_field",
    [
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
    ],
)
def test_photo_analyze_request_rejects_raw_image_content_fields(
    forbidden_field: str,
) -> None:
    payload = _valid_request_payload()
    payload[forbidden_field] = "forbidden"

    with pytest.raises(ValidationError, match="raw image content is not allowed"):
        PhotoAnalyzeRequest.model_validate(payload)


def test_photo_analyze_response_supports_all_decisions_and_metrics() -> None:
    metrics = {
        "kcal": _metric(520),
        "protein_g": _metric(36),
        "carbs_g": _metric(48),
        "fat_g": _metric(18),
        "sugar_g": _metric(8),
        "sodium_mg": _metric(640),
        "fiber_g": _metric(7),
    }
    for decision in ("ACCEPT", "WARN", "CLARIFY", "BLOCK"):
        response = PhotoAnalyzeResponse.model_validate(
            {
                "request_id": "req_123",
                "decision": decision,
                "reasons": [],
                "metrics": metrics,
            }
        )
        assert response.decision == decision
        assert response.metrics is not None
        assert response.metrics.kcal.best_estimate == 520
        assert response.metrics.protein_g.best_estimate == 36
        assert response.metrics.carbs_g.best_estimate == 48
        assert response.metrics.fat_g.best_estimate == 18
        assert response.metrics.sugar_g.best_estimate == 8
        assert response.metrics.sodium_mg.best_estimate == 640
        assert response.metrics.fiber_g.best_estimate == 7
