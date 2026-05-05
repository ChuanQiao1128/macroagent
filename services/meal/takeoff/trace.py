from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol, runtime_checkable

from services.meal.takeoff.schemas import TraceEvent


@runtime_checkable
class TraceEmitter(Protocol):
    """Emitter interface for takeoff pipeline trace events."""

    def emit(self, event: TraceEvent) -> None:
        """Emit one trace event."""


class InMemoryTraceEmitter:
    """Small in-memory emitter useful for local stage stubs and tests."""

    def __init__(self) -> None:
        self._events: list[TraceEvent] = []

    @property
    def events(self) -> tuple[TraceEvent, ...]:
        return tuple(self._events)

    def emit(self, event: TraceEvent) -> None:
        self._events.append(event)

    def get_trace(self, trace_id: str) -> tuple[TraceEvent, ...]:
        return tuple(event for event in self._events if event.trace_id == trace_id)


def emit_stage_event(
    emitter: TraceEmitter,
    *,
    trace_id: str,
    stage: str,
    event_name: str,
    image_sha256: str | None = None,
    meal_id: str | None = None,
    component_id: str | None = None,
    user_accepted_wide_range: bool | None = None,
    user_decline_clarify_reason: str | None = None,
    payload: Mapping[str, object] | None = None,
) -> TraceEvent:
    """Build and emit a standard TraceEvent for one takeoff stage."""
    event = TraceEvent(
        trace_id=trace_id,
        stage=stage,
        event_name=event_name,
        image_sha256=image_sha256,
        meal_id=meal_id,
        component_id=component_id,
        user_accepted_wide_range=user_accepted_wide_range,
        user_decline_clarify_reason=user_decline_clarify_reason,
        payload=dict(payload) if payload is not None else {},
    )
    emitter.emit(event)
    return event


__all__ = [
    "InMemoryTraceEmitter",
    "TraceEmitter",
    "emit_stage_event",
]
