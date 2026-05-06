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
_BASE64_DATA_URL_PATTERN = re.compile(r"^data:image/[a-zA-Z0-9.+-]+;base64,", re.IGNORECASE)
_BASE64_BLOB_PATTERN = re.compile(r"^[A-Za-z0-9+/=\s]{64,}$")


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
    _reject_base64_image_content(
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

    barcode_payload = (metadata.barcode_payload or "").strip()
    barcode_detected = bool(barcode_payload)
    barcode_value_stored = barcode_detected and barcode_marked_safe

    artifact: dict[str, object] = {
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
        "barcode_detected": barcode_detected,
        "barcode_value_stored": barcode_value_stored,
        "ocr_detected": bool(metadata.ocr_text_snippets),
        "ocr_text_stored": False,
        "model_version": model_version,
        "prompt_version": prompt_version,
    }
    if barcode_value_stored:
        artifact["barcode_value"] = barcode_payload
    return artifact


def _reject_ocr_pii(snippets: Sequence[str]) -> None:
    for snippet in snippets:
        normalized = snippet.strip()
        if not normalized:
            continue
        if _EMAIL_PATTERN.search(normalized) or _LONG_DIGIT_PATTERN.search(normalized):
            raise ValueError("raw OCR text appears to contain PII and cannot be persisted")
        if _LOCAL_PATH_PATTERN.search(normalized):
            raise ValueError("local filesystem paths are not allowed in capture trace artifacts")
        if _looks_like_base64_image_content(normalized):
            raise ValueError("base64 image content is not allowed in capture trace artifacts")


def _reject_local_paths(values: Sequence[str]) -> None:
    for value in values:
        normalized = value.strip()
        if not normalized:
            continue
        if _LOCAL_PATH_PATTERN.search(normalized):
            raise ValueError("local filesystem paths are not allowed in capture trace artifacts")


def _reject_base64_image_content(values: Sequence[str]) -> None:
    for value in values:
        normalized = value.strip()
        if not normalized:
            continue
        if _looks_like_base64_image_content(normalized):
            raise ValueError("base64 image content is not allowed in capture trace artifacts")


def _looks_like_base64_image_content(value: str) -> bool:
    if _BASE64_DATA_URL_PATTERN.search(value):
        return True
    if not _BASE64_BLOB_PATTERN.fullmatch(value):
        return False
    compact = "".join(value.split())
    if len(compact) < 64:
        return False
    allowed_chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/="
    return all(char in allowed_chars for char in compact)


__all__ = ["build_sanitized_capture_trace_artifact"]
