from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from services.meal.takeoff.schemas import TraceEvent
from services.meal.takeoff.trace import InMemoryTraceEmitter, TraceEmitter, emit_stage_event
from services.storage.trace_store import TraceStore


def test_trace_event_defaults_to_pii_safe_true() -> None:
    event = TraceEvent(trace_id="trace-1", stage="detect_components", event_name="started")

    assert event.pii_safe is True


def test_trace_event_schema_excludes_raw_image_fields() -> None:
    forbidden_field_names = {
        "raw_image",
        "raw_image_base64",
        "raw_image_bytes",
        "image_base64",
        "image_bytes",
        "image_data",
    }

    assert forbidden_field_names.isdisjoint(TraceEvent.model_fields)
    assert "image_sha256" in TraceEvent.model_fields

    with pytest.raises(ValidationError):
        TraceEvent(
            trace_id="trace-1",
            stage="detect_components",
            event_name="started",
            raw_image_base64="secret",
        )


def test_trace_event_decline_reason_requires_declined_wide_range() -> None:
    with pytest.raises(ValidationError):
        TraceEvent(
            trace_id="trace-1",
            stage="ask_clarification",
            event_name="user_declined",
            user_accepted_wide_range=True,
            user_decline_clarify_reason="skip",
        )


def test_takeoff_stage_stubs_can_emit_trace_events() -> None:
    emitter = InMemoryTraceEmitter()

    first = emit_stage_event(
        emitter,
        trace_id="trace-1",
        stage="detect_components",
        event_name="started",
        image_sha256="abc123",
    )
    second = emit_stage_event(
        emitter,
        trace_id="trace-1",
        stage="estimate_portions",
        event_name="completed",
        payload={"component_count": 2},
    )
    emit_stage_event(
        emitter,
        trace_id="trace-2",
        stage="detect_components",
        event_name="started",
    )

    assert first.image_sha256 == "abc123"
    assert first.trace_id == "trace-1"
    assert second.payload == {"component_count": 2}
    assert emitter.get_trace("trace-1") == (first, second)


def test_in_memory_emitter_satisfies_trace_emitter_protocol() -> None:
    emitter = InMemoryTraceEmitter()

    assert isinstance(emitter, TraceEmitter)


def test_trace_store_appends_and_returns_events_by_trace_id() -> None:
    store = TraceStore()
    original = TraceEvent(
        trace_id="trace-1",
        stage="estimate_portions",
        event_name="completed",
        payload={"component_count": 2},
    )

    store.append(original)
    original.payload["component_count"] = 99

    stored = store.get_trace("trace-1")
    assert len(stored) == 1
    assert stored[0].payload == {"component_count": 2}
    assert store.get_trace("unknown-trace") == ()


def test_trace_store_rejects_non_pii_safe_events() -> None:
    store = TraceStore()
    event = TraceEvent(
        trace_id="trace-1",
        stage="detect_components",
        event_name="started",
        pii_safe=False,
    )

    with pytest.raises(ValueError, match="pii_safe"):
        store.append(event)


def test_trace_store_rejects_forbidden_raw_image_payload_keys() -> None:
    store = TraceStore()
    event = TraceEvent(
        trace_id="trace-1",
        stage="detect_components",
        event_name="started",
        payload={"raw_image": "base64bytes"},
    )

    with pytest.raises(ValueError, match="forbidden raw-image keys"):
        store.append(event)


@pytest.mark.parametrize(
    "forbidden_key",
    [
        "image",
        "image_base64",
        "image_bytes",
        "image_data",
        "raw_image",
        "raw_image_base64",
        "raw_image_bytes",
    ],
)
def test_trace_store_rejects_all_forbidden_raw_image_payload_keys(
    forbidden_key: str,
) -> None:
    store = TraceStore()
    event = TraceEvent(
        trace_id="trace-1",
        stage="detect_components",
        event_name="started",
        payload={forbidden_key: "secret"},
    )

    with pytest.raises(ValueError, match="forbidden raw-image keys"):
        store.append(event)


def test_trace_store_accepts_image_sha256_without_raw_image_payload() -> None:
    store = TraceStore()
    event = TraceEvent(
        trace_id="trace-1",
        stage="detect_components",
        event_name="started",
        image_sha256="abc123",
        payload={"component_count": 1},
    )

    store.append(event)
    stored = store.get_trace("trace-1")

    assert len(stored) == 1
    assert stored[0].image_sha256 == "abc123"


@pytest.mark.parametrize(
    "forbidden_key",
    ["barcode_payload", "ocr_text_snippets", "local_image_path"],
)
def test_trace_store_rejects_nested_forbidden_capture_payload_keys(forbidden_key: str) -> None:
    store = TraceStore()
    event = TraceEvent(
        trace_id="trace-1",
        stage="CaptureScaleEvidenceAdapter",
        event_name="capture.scale_evidence_resolved",
        payload={
            "capture_artifact": {
                "image_identity": {"image_sha256": "abc123"},
                forbidden_key: "x",
            }
        },
    )

    with pytest.raises(ValueError, match="forbidden raw-image keys"):
        store.append(event)


def test_privacy_trace_boundary_doc_exists_and_mentions_image_hash_contract() -> None:
    doc_path = Path("docs/privacy_trace_boundary.md")

    assert doc_path.exists(), "Missing docs/privacy_trace_boundary.md"
    contents = doc_path.read_text(encoding="utf-8").lower()

    assert "pii_safe" in contents
    assert "image_sha256" in contents
    assert "raw image" in contents or "raw_image" in contents
