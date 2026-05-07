from __future__ import annotations

from datetime import UTC, datetime

import pytest

from services.capture import DeviceCaptureMetadata, resolve_scale_evidence_from_capture
from services.meal.takeoff.trace import InMemoryTraceEmitter

_CONFIDENCE_RANK = {"none": 0, "low": 1, "medium": 2, "high": 3}


def _metadata(**overrides: object) -> DeviceCaptureMetadata:
    payload = {
        "device_model": "iPhone15,3",
        "os_version": "iOS 18.1",
        "camera_position": "back",
        "orientation": "portrait",
        "pitch_degrees": 0.0,
        "roll_degrees": 0.0,
        "focal_length_mm": 5.7,
        "lens_hint": "wide",
        "depth_available": False,
        "depth_quality": "none",
        "lidar_available": False,
        "barcode_payload": None,
        "ocr_text_snippets": [],
        "reference_object_hint": None,
        "capture_timestamp": datetime(2026, 5, 1, 12, 34, 56, tzinfo=UTC),
    }
    payload.update(overrides)
    return DeviceCaptureMetadata.model_validate(payload)


def _resolution(result):
    assert len(result.resolutions) == 1
    return result.resolutions[0]


def test_depth_lidar_confidence_is_stronger_than_photo_only_reference() -> None:
    depth_result = resolve_scale_evidence_from_capture(
        trace_id="trace-depth",
        capture_metadata=_metadata(
            depth_available=True,
            lidar_available=True,
            depth_quality="high",
        ),
    )
    photo_only_result = resolve_scale_evidence_from_capture(
        trace_id="trace-photo-only",
        capture_metadata=_metadata(reference_object_hint="plate"),
    )

    depth_resolution = _resolution(depth_result)
    photo_only_resolution = _resolution(photo_only_result)

    assert depth_resolution.selected_candidate_id == "scale:lidar_depth:1"
    assert depth_resolution.scale_confidence == "high"
    assert _CONFIDENCE_RANK[depth_resolution.scale_confidence] > _CONFIDENCE_RANK[
        photo_only_resolution.scale_confidence
    ]


def test_arkit_scene_depth_is_preferred_over_photo_depth_and_reference() -> None:
    result = resolve_scale_evidence_from_capture(
        trace_id="trace-arkit-depth",
        capture_metadata=_metadata(
            depth_available=True,
            depth_quality="high",
            lidar_available=True,
            arkit_scene_depth_supported=True,
            arkit_smoothed_scene_depth_supported=True,
            arkit_depth_available=True,
            arkit_depth_quality="high",
            arkit_depth_map_width_px=256,
            arkit_depth_map_height_px=192,
            arkit_confidence_coverage=0.88,
            camera_intrinsics_available=True,
            reference_object_hint="fork",
        ),
    )

    resolution = _resolution(result)

    assert resolution.selected_candidate_id == "scale:arkit_scene_depth:1"
    assert resolution.status == "confirmed"
    assert resolution.scale_confidence == "high"
    assert resolution.expected_range_reduction_kcal == 60.0
    assert [candidate.evidence_id for candidate in result.candidates][:2] == [
        "scale:arkit_scene_depth:1",
        "scale:lidar_depth:1",
    ]


def test_arkit_scene_depth_requires_usable_quality_and_intrinsics() -> None:
    result = resolve_scale_evidence_from_capture(
        trace_id="trace-arkit-missing-intrinsics",
        capture_metadata=_metadata(
            arkit_scene_depth_supported=True,
            arkit_depth_available=True,
            arkit_depth_quality="high",
            arkit_depth_map_width_px=256,
            arkit_depth_map_height_px=192,
            arkit_confidence_coverage=0.9,
            camera_intrinsics_available=False,
        ),
    )

    candidate = next(
        candidate
        for candidate in result.candidates
        if candidate.evidence_type == "arkit_scene_depth"
    )
    resolution = _resolution(result)

    assert candidate.usable_for_scale is False
    assert candidate.rejection_reason == "camera_intrinsics_missing"
    assert resolution.status == "missing_needs_reference"


def test_barcode_metadata_maps_to_barcode_scale_evidence() -> None:
    result = resolve_scale_evidence_from_capture(
        trace_id="trace-barcode",
        capture_metadata=_metadata(barcode_payload="0123456789012"),
    )

    resolution = _resolution(result)

    assert resolution.selected_candidate_id == "scale:barcode_serving:1"
    assert resolution.status == "confirmed"
    assert resolution.scale_confidence == "medium"
    assert any(candidate.evidence_type == "barcode_serving" for candidate in result.candidates)


def test_label_metadata_maps_to_label_scale_evidence() -> None:
    result = resolve_scale_evidence_from_capture(
        trace_id="trace-label",
        capture_metadata=_metadata(ocr_text_snippets=["Nutrition Facts", "Per serving"]),
    )

    resolution = _resolution(result)

    assert resolution.selected_candidate_id == "scale:label_ocr_serving:1"
    assert resolution.status == "confirmed"
    assert resolution.scale_confidence == "medium"
    assert any(candidate.evidence_type == "label_ocr_serving" for candidate in result.candidates)


def test_reference_hints_produce_weak_or_medium_evidence_signals() -> None:
    result = resolve_scale_evidence_from_capture(
        trace_id="trace-reference",
        capture_metadata=_metadata(reference_object_hint="fork"),
    )

    resolution = _resolution(result)
    reference_candidate = next(
        candidate
        for candidate in result.candidates
        if candidate.evidence_type == "reference_object"
    )

    assert reference_candidate.confidence_label == "medium"
    assert resolution.status == "weak"
    assert resolution.scale_confidence == "low"


def test_explicit_container_hint_maps_to_personal_container_scale_evidence() -> None:
    result = resolve_scale_evidence_from_capture(
        trace_id="trace-container",
        capture_metadata=_metadata(reference_object_hint="container_rice_bowl_300ml"),
    )

    resolution = _resolution(result)
    container_candidate = next(
        candidate
        for candidate in result.candidates
        if candidate.evidence_type == "personal_container"
    )

    assert container_candidate.evidence_id == (
        "scale:manual_container:container_rice_bowl_300ml"
    )
    assert container_candidate.detection_source == "user_selected"
    assert resolution.selected_candidate_id == container_candidate.evidence_id
    assert resolution.status == "confirmed"
    assert resolution.scale_confidence == "medium"
    assert not any(candidate.evidence_type == "reference_object" for candidate in result.candidates)


def test_weak_side_angle_reference_prompts_for_user_reference() -> None:
    result = resolve_scale_evidence_from_capture(
        trace_id="trace-side-angle",
        capture_metadata=_metadata(reference_object_hint="fork", pitch_degrees=40.0),
    )

    resolution = _resolution(result)

    assert resolution.status == "weak"
    assert resolution.scale_confidence == "low"
    assert resolution.prompt_user_for_reference is True


def test_card_like_reference_is_rejected_for_pii_risk() -> None:
    result = resolve_scale_evidence_from_capture(
        trace_id="trace-pii",
        capture_metadata=_metadata(reference_object_hint="credit card"),
    )

    resolution = _resolution(result)
    card_candidate = next(
        candidate
        for candidate in result.candidates
        if candidate.object_type == "card_like_object"
    )

    assert card_candidate.usable_for_scale is False
    assert card_candidate.pii_risk is True
    assert resolution.status == "rejected_due_to_pii"
    assert resolution.selected_candidate_id is None
    assert resolution.prompt_user_for_reference is True


def test_missing_scale_evidence_requests_reference_when_required() -> None:
    result = resolve_scale_evidence_from_capture(
        trace_id="trace-missing",
        capture_metadata=_metadata(),
    )

    resolution = _resolution(result)

    assert result.candidates == []
    assert resolution.status == "missing_needs_reference"
    assert resolution.scale_confidence == "none"
    assert resolution.prompt_user_for_reference is True


def test_capture_scale_adapter_emits_trace_event_with_resolution_payload() -> None:
    emitter = InMemoryTraceEmitter()

    result = resolve_scale_evidence_from_capture(
        trace_id="trace-event",
        capture_metadata=_metadata(
            depth_available=True,
            lidar_available=True,
            depth_quality="medium",
        ),
        emitter=emitter,
        image_sha256="a" * 64,
    )

    resolution = _resolution(result)
    event = emitter.get_trace("trace-event")[0]

    assert event.stage == "CaptureScaleEvidenceAdapter"
    assert event.event_name == "capture.scale_evidence_resolved"
    assert event.image_sha256 == "a" * 64
    assert event.payload == {
        "candidate_count": len(result.candidates),
        "selected_candidate_id": resolution.selected_candidate_id,
        "resolution_status": resolution.status,
        "scale_confidence": resolution.scale_confidence,
        "prompt_user_for_reference": resolution.prompt_user_for_reference,
        "arkit_depth_available": False,
        "arkit_depth_quality": "none",
        "arkit_confidence_coverage": None,
    }


@pytest.mark.parametrize(
    "depth_quality,expected_usable",
    [("high", True), ("medium", True), ("low", False), ("none", False), ("unknown", False)],
)
def test_depth_candidate_usability_is_deterministic_by_quality(
    depth_quality: str,
    expected_usable: bool,
) -> None:
    result = resolve_scale_evidence_from_capture(
        trace_id=f"trace-depth-{depth_quality}",
        capture_metadata=_metadata(
            depth_available=True,
            lidar_available=True,
            depth_quality=depth_quality,
        ),
    )

    lidar_candidate = next(
        candidate
        for candidate in result.candidates
        if candidate.evidence_type == "lidar_depth"
    )

    assert lidar_candidate.usable_for_scale is expected_usable
