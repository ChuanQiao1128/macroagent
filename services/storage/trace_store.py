from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Mapping, Sequence

from services.meal.takeoff.schemas import TraceEvent

_FORBIDDEN_IMAGE_KEYS = frozenset(
    {
        "image",
        "image_b64",
        "image_base64",
        "image_bytes",
        "image_data",
        "raw_image",
        "raw_image_base64",
        "raw_image_bytes",
        "base64_image",
        "base64",
        "base64_data",
        "base64_payload",
        "local_image_path",
        "image_path",
        "path",
        "local_path",
        "filesystem_path",
        "ocr_text",
        "ocr_raw_text",
        "ocr_text_snippets",
        "barcode_payload",
    }
)
_LOCAL_PATH_PATTERN = re.compile(r"(^~?/)|(^/Users/)|(^/private/)|(^/var/)|(^[A-Za-z]:\\)|(^\\\\)")
_BASE64_DATA_URL_PATTERN = re.compile(r"^data:image/[a-zA-Z0-9.+-]+;base64,", re.IGNORECASE)
_BASE64_BLOB_PATTERN = re.compile(r"^[A-Za-z0-9+/=\s]{64,}$")


class TraceStore:
    """In-memory trace store for append/read access during local development."""

    def __init__(self) -> None:
        self._events_by_trace_id: dict[str, list[TraceEvent]] = defaultdict(list)

    def append(self, event: TraceEvent) -> None:
        if not event.pii_safe:
            raise ValueError("TraceStore only accepts pii_safe trace events")
        forbidden_keys = _collect_forbidden_keys(event.payload)
        if forbidden_keys:
            joined_keys = ", ".join(sorted(forbidden_keys))
            raise ValueError(f"TraceEvent payload contains forbidden raw-image keys: {joined_keys}")
        if _contains_forbidden_values(event.payload):
            raise ValueError(
                "TraceEvent payload contains forbidden raw-image content values"
            )
        self._events_by_trace_id[event.trace_id].append(event.model_copy(deep=True))

    def get_trace(self, trace_id: str) -> tuple[TraceEvent, ...]:
        return tuple(self._events_by_trace_id.get(trace_id, ()))


def _collect_forbidden_keys(payload: object) -> set[str]:
    forbidden: set[str] = set()
    if isinstance(payload, Mapping):
        for key, value in payload.items():
            if key in _FORBIDDEN_IMAGE_KEYS:
                forbidden.add(key)
            forbidden.update(_collect_forbidden_keys(value))
        return forbidden
    if isinstance(payload, Sequence) and not isinstance(payload, str | bytes | bytearray):
        for value in payload:
            forbidden.update(_collect_forbidden_keys(value))
    return forbidden


def _contains_forbidden_values(payload: object) -> bool:
    if isinstance(payload, str):
        normalized = payload.strip()
        if not normalized:
            return False
        has_local_path = _LOCAL_PATH_PATTERN.search(normalized) is not None
        has_base64_blob = _looks_like_base64_image_content(normalized)
        return has_local_path or has_base64_blob
    if isinstance(payload, Mapping):
        barcode_value = payload.get("barcode_value")
        if barcode_value is not None and payload.get("barcode_value_stored") is not True:
            return True
        return any(_contains_forbidden_values(value) for value in payload.values())
    if isinstance(payload, Sequence) and not isinstance(payload, str | bytes | bytearray):
        return any(_contains_forbidden_values(value) for value in payload)
    return False


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


__all__ = ["TraceStore"]
