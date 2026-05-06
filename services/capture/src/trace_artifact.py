from __future__ import annotations

import re
from collections.abc import Sequence

from services.capture.src.schemas import PhotoAnalyzeRequest
from services.meal.takeoff.schemas import MealScaleEvidence

_LOCAL_PATH_PATTERN = re.compile(
    r"(^~?/)|(^/Users/)|(^/private/)|(^/var/)|(^[A-Za-z]:\\)|(^\\\\)"
)
_EMAIL_PATTERN = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_LONG_DIGIT_PATTERN = re.compile(r"\d{9,}")


def build_sanitized_capture_trace_artifact(
    *,
    request: PhotoAnalyzeRequest,
    scale_evidence: MealScaleEvidence,
    model_version: str | None = None,
    prompt_version: str | None = None,
    barcode_marked_safe: bool = False,
) -> dict[str, object]:
    """Build a PII-safe capture trace payload from a photo analyze request."""
    metadata = request.capture_metadata
    _reject_local_paths(
        [
            metadata.barcode_payload or "",
            metadata.reference_object_hint or "",
            metadata.lens_hint or "",
        ]
    )
    _reject_ocr_pii(metadata.ocr_text_snippets)

    resolution = scale_evidence.resolutions[0]
    selected_scale_ids = (
        [resolution.selected_candidate_id] if resolution.selected_candidate_id else []
    )

    capture_quality_summary: dict[str, object] = {
        "depth_available": metadata.depth_available,
        "depth_quality": metadata.depth_quality,
        "lidar_available": metadata.lidar_available,
        "camera_position": metadata.camera_position,
        "orientation": metadata.orientation,
        "pitch_degrees": round(metadata.pitch_degrees, 1),
        "roll_degrees": round(metadata.roll_degrees, 1),
    }
    if metadata.lens_hint:
        capture_quality_summary["lens_hint"] = metadata.lens_hint

    return {
        "image_identity": {
            "image_sha256": request.image_identity.image_sha256,
            "image_format": request.image_identity.image_format,
            "width_px": request.image_identity.width_px,
            "height_px": request.image_identity.height_px,
            "byte_size": request.image_identity.byte_size,
        },
        "capture_quality_summary": capture_quality_summary,
        "scale_evidence_ids": sorted(
            {
                candidate.evidence_id
                for candidate in scale_evidence.candidates
                if candidate.usable_for_scale
            }
            | set(selected_scale_ids)
        ),
        "barcode_detected": bool((metadata.barcode_payload or "").strip()),
        "barcode_value_stored": bool((metadata.barcode_payload or "").strip())
        and barcode_marked_safe,
        "ocr_detected": bool(metadata.ocr_text_snippets),
        "ocr_text_stored": False,
        "model_version": model_version,
        "prompt_version": prompt_version,
    }


def _reject_ocr_pii(snippets: Sequence[str]) -> None:
    for snippet in snippets:
        normalized = snippet.strip()
        if not normalized:
            continue
        if _EMAIL_PATTERN.search(normalized) or _LONG_DIGIT_PATTERN.search(normalized):
            raise ValueError("raw OCR text appears to contain PII and cannot be persisted")
        if _LOCAL_PATH_PATTERN.search(normalized):
            raise ValueError("local filesystem paths are not allowed in capture trace artifacts")


def _reject_local_paths(values: Sequence[str]) -> None:
    for value in values:
        normalized = value.strip()
        if not normalized:
            continue
        if _LOCAL_PATH_PATTERN.search(normalized):
            raise ValueError("local filesystem paths are not allowed in capture trace artifacts")


__all__ = ["build_sanitized_capture_trace_artifact"]
