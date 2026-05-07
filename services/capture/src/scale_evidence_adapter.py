from __future__ import annotations

from collections.abc import Iterable

from services.capture.src.schemas import DeviceCaptureMetadata
from services.meal.takeoff.schemas import (
    MealScaleEvidence,
    ScaleEvidenceCandidate,
    ScaleEvidenceResolution,
)
from services.meal.takeoff.trace import TraceEmitter, emit_stage_event

_ADAPTER_STAGE = "CaptureScaleEvidenceAdapter"
_POLICY_REFS = ["scale_evidence_policy_v0.3", "capture_metadata_v0.1"]

_CARD_PII_TOKENS = {
    "credit card",
    "debit card",
    "bank card",
    "visa card",
    "mastercard",
    "amex",
    "american express",
    "driver license",
    "driver's license",
    "driver licence",
    "drivers license",
    "drivers licence",
    "id card",
    "id badge",
    "student id",
    "identity card",
    "passport",
}
_REFERENCE_MEDIUM_TOKENS = {
    "calibration card",
    "ruler",
    "measuring tape",
    "chopstick",
    "fork",
    "knife",
    "spoon",
    "teaspoon",
    "tablespoon",
}
_REFERENCE_WEAK_TOKENS = {
    "plate",
    "bowl",
    "cup",
    "mug",
    "phone",
    "hand",
}
_MANUAL_CONTAINER_PREFIX = "container_"
_LABEL_TOKENS = {
    "nutrition facts",
    "serving",
    "servings",
    "per 100g",
    "per serving",
    "kcal",
    "calories",
}


def resolve_scale_evidence_from_capture(
    *,
    trace_id: str,
    capture_metadata: DeviceCaptureMetadata,
    emitter: TraceEmitter | None = None,
    image_sha256: str | None = None,
) -> MealScaleEvidence:
    """Map iPhone capture metadata to deterministic scale evidence objects."""
    candidates: list[ScaleEvidenceCandidate] = []

    arkit_candidate = _build_arkit_scene_depth_candidate(capture_metadata)
    if arkit_candidate is not None:
        candidates.append(arkit_candidate)

    lidar_candidate = _build_lidar_candidate(capture_metadata)
    if lidar_candidate is not None:
        candidates.append(lidar_candidate)

    barcode_candidate = _build_barcode_candidate(capture_metadata)
    if barcode_candidate is not None:
        candidates.append(barcode_candidate)

    label_candidate = _build_label_candidate(capture_metadata)
    if label_candidate is not None:
        candidates.append(label_candidate)

    container_candidate = _build_personal_container_candidate(capture_metadata)
    if container_candidate is not None:
        candidates.append(container_candidate)

    reference_candidate = _build_reference_candidate(capture_metadata)
    if reference_candidate is not None:
        candidates.append(reference_candidate)

    resolution = _resolve(candidates=candidates, capture_metadata=capture_metadata)
    result = MealScaleEvidence(candidates=candidates, resolutions=[resolution])

    if emitter is not None:
        emit_stage_event(
            emitter,
            trace_id=trace_id,
            stage=_ADAPTER_STAGE,
            event_name="capture.scale_evidence_resolved",
            image_sha256=image_sha256,
            payload={
                "candidate_count": len(candidates),
                "selected_candidate_id": resolution.selected_candidate_id,
                "resolution_status": resolution.status,
                "scale_confidence": resolution.scale_confidence,
                "prompt_user_for_reference": resolution.prompt_user_for_reference,
                "arkit_depth_available": capture_metadata.arkit_depth_available,
                "arkit_depth_quality": capture_metadata.arkit_depth_quality,
                "arkit_confidence_coverage": capture_metadata.arkit_confidence_coverage,
            },
        )

    return result


def _build_arkit_scene_depth_candidate(
    metadata: DeviceCaptureMetadata,
) -> ScaleEvidenceCandidate | None:
    if not metadata.arkit_scene_depth_supported and not metadata.arkit_depth_available:
        return None

    if metadata.arkit_depth_quality in {"high", "medium"}:
        confidence_label = "high" if metadata.arkit_depth_quality == "high" else "medium"
        confidence_score = 0.96 if metadata.arkit_depth_quality == "high" else 0.86
        usable = True
        rejection_reason = None
    else:
        confidence_label = "low"
        confidence_score = 0.42
        usable = False
        rejection_reason = "arkit_depth_quality_insufficient"

    if metadata.arkit_depth_available and not metadata.camera_intrinsics_available:
        confidence_score = min(confidence_score, 0.58)
        usable = False
        rejection_reason = "camera_intrinsics_missing"

    return ScaleEvidenceCandidate(
        evidence_id="scale:arkit_scene_depth:1",
        evidence_type="arkit_scene_depth",
        object_type="scene_depth_map",
        detection_source="device_depth",
        confidence_label=confidence_label,
        confidence_score=confidence_score,
        usable_for_scale=usable,
        rejection_reason=rejection_reason,
    )


def _build_lidar_candidate(metadata: DeviceCaptureMetadata) -> ScaleEvidenceCandidate | None:
    if not metadata.lidar_available and not metadata.depth_available:
        return None

    if metadata.depth_quality in {"high", "medium"}:
        confidence_label = "high" if metadata.depth_quality == "high" else "medium"
        confidence_score = 0.95 if metadata.depth_quality == "high" else 0.82
        usable = True
    else:
        confidence_label = "low"
        confidence_score = 0.45
        usable = False

    return ScaleEvidenceCandidate(
        evidence_id="scale:lidar_depth:1",
        evidence_type="lidar_depth",
        object_type="scene_depth",
        detection_source="vision_agent",
        confidence_label=confidence_label,
        confidence_score=confidence_score,
        usable_for_scale=usable,
        rejection_reason=None if usable else "depth_quality_insufficient",
    )


def _build_barcode_candidate(metadata: DeviceCaptureMetadata) -> ScaleEvidenceCandidate | None:
    payload = (metadata.barcode_payload or "").strip()
    if not payload:
        return None
    return ScaleEvidenceCandidate(
        evidence_id="scale:barcode_serving:1",
        evidence_type="barcode_serving",
        object_type="barcode",
        detection_source="barcode",
        confidence_label="high",
        confidence_score=0.9,
        usable_for_scale=True,
    )


def _build_label_candidate(metadata: DeviceCaptureMetadata) -> ScaleEvidenceCandidate | None:
    if not _contains_any(metadata.ocr_text_snippets, _LABEL_TOKENS):
        return None
    return ScaleEvidenceCandidate(
        evidence_id="scale:label_ocr_serving:1",
        evidence_type="label_ocr_serving",
        object_type="nutrition_label",
        detection_source="label_ocr",
        confidence_label="medium",
        confidence_score=0.75,
        usable_for_scale=True,
    )


def _build_personal_container_candidate(
    metadata: DeviceCaptureMetadata,
) -> ScaleEvidenceCandidate | None:
    hint = (metadata.reference_object_hint or "").strip().lower()
    if not hint.startswith(_MANUAL_CONTAINER_PREFIX):
        return None

    return ScaleEvidenceCandidate(
        evidence_id=f"scale:manual_container:{hint}",
        evidence_type="personal_container",
        object_type=hint,
        detection_source="user_selected",
        confidence_label="medium",
        confidence_score=0.78,
        usable_for_scale=True,
    )


def _build_reference_candidate(metadata: DeviceCaptureMetadata) -> ScaleEvidenceCandidate | None:
    hint = (metadata.reference_object_hint or "").strip().lower()
    if not hint:
        return None
    if hint.startswith(_MANUAL_CONTAINER_PREFIX):
        return None

    if _is_pii_card_like_reference(hint):
        return ScaleEvidenceCandidate(
            evidence_id="scale:reference_object:1",
            evidence_type="reference_object",
            object_type="card_like_object",
            detection_source="vision_agent",
            confidence_label="low",
            confidence_score=0.2,
            pii_risk=True,
            usable_for_scale=False,
            rejection_reason="card_like_object_pii_risk",
        )

    if any(token in hint for token in _REFERENCE_MEDIUM_TOKENS):
        confidence_label = "medium"
        confidence_score = 0.7
    elif any(token in hint for token in _REFERENCE_WEAK_TOKENS):
        confidence_label = "low"
        confidence_score = 0.52
    else:
        confidence_label = "low"
        confidence_score = 0.48

    return ScaleEvidenceCandidate(
        evidence_id="scale:reference_object:1",
        evidence_type="reference_object",
        object_type=hint,
        detection_source="vision_agent",
        confidence_label=confidence_label,
        confidence_score=confidence_score,
        usable_for_scale=True,
    )


def _resolve(
    *,
    candidates: list[ScaleEvidenceCandidate],
    capture_metadata: DeviceCaptureMetadata,
) -> ScaleEvidenceResolution:
    candidate_ids = [candidate.evidence_id for candidate in candidates]

    selected = _select_preferred_usable_candidate(candidates)
    if selected is not None:
        weak_side_angle = abs(capture_metadata.pitch_degrees) >= 35
        if weak_side_angle and selected.evidence_type == "reference_object":
            return ScaleEvidenceResolution(
                resolution_id="scale_resolution:capture:1",
                status="weak",
                candidate_ids=candidate_ids,
                selected_candidate_id=selected.evidence_id,
                scale_confidence="low",
                expected_range_reduction_kcal=12.0,
                prompt_user_for_reference=True,
                trace_message="Reference object available but side angle is weak for calibration.",
                policy_refs=_POLICY_REFS,
            )

        if selected.evidence_type == "arkit_scene_depth":
            return ScaleEvidenceResolution(
                resolution_id="scale_resolution:capture:1",
                status="confirmed",
                candidate_ids=candidate_ids,
                selected_candidate_id=selected.evidence_id,
                scale_confidence="high",
                expected_range_reduction_kcal=60.0,
                prompt_user_for_reference=False,
                trace_message="ARKit scene-depth metadata confirmed and selected for scale.",
                policy_refs=_POLICY_REFS,
            )

        if selected.evidence_type == "lidar_depth":
            return ScaleEvidenceResolution(
                resolution_id="scale_resolution:capture:1",
                status="confirmed",
                candidate_ids=candidate_ids,
                selected_candidate_id=selected.evidence_id,
                scale_confidence="high",
                expected_range_reduction_kcal=45.0,
                prompt_user_for_reference=False,
                trace_message="LiDAR/depth metadata confirmed and used for scale.",
                policy_refs=_POLICY_REFS,
            )

        if selected.evidence_type in {"barcode_serving", "label_ocr_serving"}:
            return ScaleEvidenceResolution(
                resolution_id="scale_resolution:capture:1",
                status="confirmed",
                candidate_ids=candidate_ids,
                selected_candidate_id=selected.evidence_id,
                scale_confidence="medium",
                expected_range_reduction_kcal=28.0,
                prompt_user_for_reference=False,
                trace_message="Barcode/label serving metadata selected for scale evidence.",
                policy_refs=_POLICY_REFS,
            )

        if selected.evidence_type == "personal_container":
            return ScaleEvidenceResolution(
                resolution_id="scale_resolution:capture:1",
                status="confirmed",
                candidate_ids=candidate_ids,
                selected_candidate_id=selected.evidence_id,
                scale_confidence="medium",
                expected_range_reduction_kcal=35.0,
                prompt_user_for_reference=False,
                trace_message="User-selected known container metadata selected for scale.",
                policy_refs=_POLICY_REFS,
            )

        return ScaleEvidenceResolution(
            resolution_id="scale_resolution:capture:1",
            status="weak",
            candidate_ids=candidate_ids,
            selected_candidate_id=selected.evidence_id,
            scale_confidence="low",
            expected_range_reduction_kcal=15.0,
            prompt_user_for_reference=False,
            trace_message="Reference object hint selected as weak scale evidence.",
            policy_refs=_POLICY_REFS,
        )

    pii_candidate = next(
        (
            candidate
            for candidate in candidates
            if candidate.pii_risk and candidate.rejection_reason == "card_like_object_pii_risk"
        ),
        None,
    )
    if pii_candidate is not None:
        return ScaleEvidenceResolution(
            resolution_id="scale_resolution:capture:1",
            status="rejected_due_to_pii",
            candidate_ids=candidate_ids,
            selected_candidate_id=None,
            scale_confidence="none",
            expected_range_reduction_kcal=None,
            prompt_user_for_reference=True,
            trace_message="Rejected card-like reference object due to PII risk.",
            policy_refs=_POLICY_REFS,
        )

    return ScaleEvidenceResolution(
        resolution_id="scale_resolution:capture:1",
        status="missing_needs_reference",
        candidate_ids=candidate_ids,
        selected_candidate_id=None,
        scale_confidence="none",
        expected_range_reduction_kcal=None,
        prompt_user_for_reference=True,
        trace_message="No usable scale evidence found in capture metadata.",
        policy_refs=_POLICY_REFS,
    )


def _select_preferred_usable_candidate(
    candidates: list[ScaleEvidenceCandidate],
) -> ScaleEvidenceCandidate | None:
    priority = {
        "arkit_scene_depth": 0,
        "lidar_depth": 1,
        "personal_container": 2,
        "barcode_serving": 3,
        "label_ocr_serving": 4,
        "reference_object": 5,
    }
    usable_candidates = [candidate for candidate in candidates if candidate.usable_for_scale]
    if not usable_candidates:
        return None
    return sorted(
        usable_candidates,
        key=lambda candidate: (
            priority.get(candidate.evidence_type, 100),
            -candidate.confidence_score,
        ),
    )[0]


def _contains_any(snippets: Iterable[str], tokens: set[str]) -> bool:
    lowered = " ".join(snippets).lower()
    return any(token in lowered for token in tokens)


def _is_pii_card_like_reference(hint: str) -> bool:
    # Keep deterministic safe exceptions for explicit non-PII calibration objects.
    if "calibration card" in hint:
        return False

    if any(token in hint for token in _CARD_PII_TOKENS):
        return True

    card_pii_context_tokens = {"id", "identity", "bank", "visa", "master", "amex"}
    if "card" in hint and any(token in hint for token in card_pii_context_tokens):
        return True

    return False
