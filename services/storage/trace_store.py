from __future__ import annotations

from collections import defaultdict

from services.meal.takeoff.schemas import TraceEvent

_FORBIDDEN_IMAGE_KEYS = frozenset(
    {
        "image",
        "image_base64",
        "image_bytes",
        "image_data",
        "raw_image",
        "raw_image_base64",
        "raw_image_bytes",
        "base64_image",
        "base64",
        "local_image_path",
        "image_path",
        "path",
        "ocr_text",
        "ocr_text_snippets",
        "barcode_payload",
    }
)


class TraceStore:
    """In-memory trace store for append/read access during local development."""

    def __init__(self) -> None:
        self._events_by_trace_id: dict[str, list[TraceEvent]] = defaultdict(list)

    def append(self, event: TraceEvent) -> None:
        if not event.pii_safe:
            raise ValueError("TraceStore only accepts pii_safe trace events")
        forbidden_keys = _FORBIDDEN_IMAGE_KEYS.intersection(event.payload.keys())
        if forbidden_keys:
            joined_keys = ", ".join(sorted(forbidden_keys))
            raise ValueError(f"TraceEvent payload contains forbidden raw-image keys: {joined_keys}")
        self._events_by_trace_id[event.trace_id].append(event.model_copy(deep=True))

    def get_trace(self, trace_id: str) -> tuple[TraceEvent, ...]:
        return tuple(self._events_by_trace_id.get(trace_id, ()))


__all__ = ["TraceStore"]
