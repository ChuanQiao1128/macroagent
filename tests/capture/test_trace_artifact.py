from __future__ import annotations

from datetime import UTC, datetime

import pytest

from services.capture import (
    PhotoAnalyzeRequest,
    build_sanitized_capture_trace_artifact,
    resolve_scale_evidence_from_capture,
)


def _request_payload(
    *,
    barcode_payload: str | None = None,
    ocr_text_snippets: list[str] | None = None,
) -> dict:
    return {
        "request_id": "req_trace_artifact_1",
        "user_id": "user_trace_artifact_1",
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
            "pitch_degrees": 2.54,
            "roll_degrees": -1.03,
            "focal_length_mm": 5.7,
            "lens_hint": "wide",
            "depth_available": True,
            "depth_quality": "medium",
            "lidar_available": True,
            "barcode_payload": barcode_payload,
            "ocr_text_snippets": ocr_text_snippets or [],
            "reference_object_hint": "standard dinner plate",
            "capture_timestamp": datetime(2026, 5, 1, 12, 34, 56, tzinfo=UTC).isoformat(),
        },
    }


def _request(
    *,
    barcode_payload: str | None = None,
    ocr_text_snippets: list[str] | None = None,
) -> PhotoAnalyzeRequest:
    return PhotoAnalyzeRequest.model_validate(
        _request_payload(barcode_payload=barcode_payload, ocr_text_snippets=ocr_text_snippets)
    )


def test_build_sanitized_capture_trace_artifact_contains_only_safe_debuggable_fields() -> None:
    request = _request(barcode_payload="0123456789012", ocr_text_snippets=["Nutrition Facts"])
    scale_evidence = resolve_scale_evidence_from_capture(
        trace_id="trace-capture-safe",
        capture_metadata=request.capture_metadata,
    )

    artifact = build_sanitized_capture_trace_artifact(
        request=request,
        scale_evidence=scale_evidence,
        model_version="vision_model_placeholder",
        prompt_version="vision_prompt_placeholder",
        barcode_marked_safe=False,
    )

    assert artifact["image_identity"] == {
        "image_sha256": "a" * 64,
        "image_format": "heic",
        "width_px": 3024,
        "height_px": 4032,
        "byte_size": 2456789,
    }
    assert artifact["capture_quality_summary"] == {
        "depth_available": True,
        "depth_quality": "medium",
        "lidar_available": True,
        "camera_position": "back",
        "orientation": "portrait",
        "pitch_degrees": 2.5,
        "roll_degrees": -1.0,
        "lens_hint": "wide",
    }
    assert artifact["scale_evidence_ids"]
    assert "scale:lidar_depth:1" in artifact["scale_evidence_ids"]
    assert artifact["barcode_detected"] is True
    assert artifact["barcode_value_stored"] is False
    assert artifact["ocr_detected"] is True
    assert artifact["ocr_text_stored"] is False
    assert artifact["model_version"] == "vision_model_placeholder"
    assert artifact["prompt_version"] == "vision_prompt_placeholder"
    assert "image_bytes" not in artifact
    assert "image_base64" not in artifact
    assert "local_image_path" not in artifact
    assert "ocr_text_snippets" not in artifact
    assert "barcode_payload" not in artifact


def test_build_sanitized_capture_trace_artifact_rejects_ocr_with_pii_risk() -> None:
    request = _request(ocr_text_snippets=["Call me at 1234567890"])
    scale_evidence = resolve_scale_evidence_from_capture(
        trace_id="trace-capture-ocr-pii",
        capture_metadata=request.capture_metadata,
    )

    with pytest.raises(ValueError, match="raw OCR text appears to contain PII"):
        build_sanitized_capture_trace_artifact(
            request=request,
            scale_evidence=scale_evidence,
        )


@pytest.mark.parametrize(
    "field,value",
    [
        ("reference_object_hint", "/Users/qc/private/meal.jpg"),
        ("barcode_payload", "~/Desktop/barcode.txt"),
    ],
)
def test_build_sanitized_capture_trace_artifact_rejects_local_paths(
    field: str,
    value: str,
) -> None:
    payload = _request_payload()
    payload["capture_metadata"][field] = value
    request = PhotoAnalyzeRequest.model_validate(payload)
    scale_evidence = resolve_scale_evidence_from_capture(
        trace_id="trace-capture-path",
        capture_metadata=request.capture_metadata,
    )

    with pytest.raises(ValueError, match="local filesystem paths are not allowed"):
        build_sanitized_capture_trace_artifact(
            request=request,
            scale_evidence=scale_evidence,
        )


def test_build_sanitized_capture_trace_artifact_stores_barcode_value_only_when_safe() -> None:
    request = _request(barcode_payload="0123456789012")
    scale_evidence = resolve_scale_evidence_from_capture(
        trace_id="trace-capture-barcode",
        capture_metadata=request.capture_metadata,
    )

    unsafe = build_sanitized_capture_trace_artifact(
        request=request,
        scale_evidence=scale_evidence,
        barcode_marked_safe=False,
    )
    safe = build_sanitized_capture_trace_artifact(
        request=request,
        scale_evidence=scale_evidence,
        barcode_marked_safe=True,
    )

    assert unsafe["barcode_detected"] is True
    assert unsafe["barcode_value_stored"] is False
    assert safe["barcode_detected"] is True
    assert safe["barcode_value_stored"] is True
