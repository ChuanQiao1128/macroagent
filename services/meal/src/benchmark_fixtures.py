from __future__ import annotations

import json
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

FixtureSegment = Literal["friendly", "regression", "adversarial"]
FixtureFamily = Literal["scale_evidence", "cross_cultural", "barcode_label_stub"]
GateName = Literal["scale_evidence", "energy_density", "evidence_arbitration"]
FixtureGroup = FixtureSegment | FixtureFamily


@dataclass(frozen=True, slots=True)
class BenchmarkFixture:
    fixture_id: str
    title: str
    gate: GateName
    segment: FixtureSegment
    groups: tuple[FixtureGroup, ...]


@dataclass(frozen=True, slots=True)
class BenchmarkFixtureResult:
    fixture_id: str | None
    segment: FixtureSegment | None
    decision: str | None
    clarify_triggered: bool
    high_conflict: bool
    silent_high_conflict: bool
    row: Mapping[str, Any]


def _fixture(
    fixture_id: str,
    title: str,
    gate: GateName,
    segment: FixtureSegment,
    *families: FixtureFamily,
) -> BenchmarkFixture:
    return BenchmarkFixture(
        fixture_id=fixture_id,
        title=title,
        gate=gate,
        segment=segment,
        groups=(segment, *families),
    )


V0_3_BENCHMARK_FIXTURES: tuple[BenchmarkFixture, ...] = (
    _fixture(
        "no_reference_low_impact",
        "No reference with low impact meal",
        "scale_evidence",
        "friendly",
        "scale_evidence",
    ),
    _fixture(
        "no_reference_high_impact_bowl",
        "No reference with high-impact bowl",
        "scale_evidence",
        "adversarial",
        "scale_evidence",
    ),
    _fixture(
        "spoon_visible_near_plate",
        "Spoon visible near plate",
        "scale_evidence",
        "friendly",
        "scale_evidence",
    ),
    _fixture(
        "fork_visible_far_from_plate",
        "Fork visible far from plate",
        "scale_evidence",
        "regression",
        "scale_evidence",
    ),
    _fixture(
        "saved_bowl_detected",
        "Saved bowl calibration detected",
        "scale_evidence",
        "friendly",
        "scale_evidence",
    ),
    _fixture(
        "barcode_packaged_food",
        "Barcode for packaged food",
        "scale_evidence",
        "friendly",
        "scale_evidence",
        "barcode_label_stub",
    ),
    _fixture(
        "card_like_object_with_pii",
        "Card-like object with PII should be rejected",
        "scale_evidence",
        "adversarial",
        "scale_evidence",
        "barcode_label_stub",
    ),
    _fixture(
        "plate_visible_unknown_size",
        "Plate visible with unknown physical size",
        "scale_evidence",
        "regression",
        "scale_evidence",
    ),
    _fixture(
        "cooked_rice_correct_density",
        "Cooked rice uses cooked density",
        "energy_density",
        "friendly",
        "cross_cultural",
    ),
    _fixture(
        "dry_rice_incorrectly_used_for_cooked_rice",
        "Dry rice density incorrectly used for cooked rice",
        "energy_density",
        "regression",
        "cross_cultural",
    ),
    _fixture(
        "sauce_mapped_to_oil",
        "Sauce mapped to oil density policy",
        "energy_density",
        "regression",
        "cross_cultural",
    ),
    _fixture(
        "mixed_bowl_aggregate_passes_component_fails",
        "Mixed bowl aggregate passes but a component fails",
        "energy_density",
        "adversarial",
        "cross_cultural",
    ),
    _fixture(
        "compatible_portion_ranges_merge",
        "Compatible portion ranges merge",
        "evidence_arbitration",
        "friendly",
        "cross_cultural",
    ),
    _fixture(
        "incompatible_macro_values_conflict",
        "Incompatible macro values conflict",
        "evidence_arbitration",
        "regression",
        "cross_cultural",
    ),
    _fixture(
        "user_correction_beats_default_prior",
        "User correction beats default prior",
        "evidence_arbitration",
        "friendly",
        "cross_cultural",
    ),
    _fixture(
        "llm_raw_macro_blocks",
        "LLM raw macro claim is blocked by arbitration",
        "evidence_arbitration",
        "adversarial",
        "cross_cultural",
    ),
)

V0_3_REQUIRED_FIXTURE_IDS: tuple[str, ...] = tuple(
    fixture.fixture_id for fixture in V0_3_BENCHMARK_FIXTURES
)


def load_fixture_results_jsonl(path: str | Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with Path(path).open(encoding="utf-8") as file_obj:
        for line_number, line in enumerate(file_obj, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            payload = json.loads(stripped)
            if not isinstance(payload, dict):
                raise ValueError(f"{path}:{line_number} must contain a JSON object")
            rows.append(payload)
    return rows


def summarize_benchmark_results(
    rows: Sequence[Mapping[str, Any]],
    fixtures: Sequence[BenchmarkFixture] = V0_3_BENCHMARK_FIXTURES,
) -> dict[str, Any]:
    fixture_index = {fixture.fixture_id: fixture for fixture in fixtures}
    normalized = [_normalize_result_row(row, fixture_index) for row in rows]

    segment_rows: dict[FixtureSegment, list[BenchmarkFixtureResult]] = {
        "friendly": [],
        "regression": [],
        "adversarial": [],
    }
    for row in normalized:
        if row.segment is not None:
            segment_rows[row.segment].append(row)

    required_ids = [fixture.fixture_id for fixture in fixtures]
    seen_fixture_ids = {
        row.fixture_id
        for row in normalized
        if row.fixture_id is not None and row.fixture_id in fixture_index
    }
    missing_fixture_ids = [
        fixture_id for fixture_id in required_ids if fixture_id not in seen_fixture_ids
    ]

    overall = _summarize_metric_slice(normalized)
    segment_summary = {
        segment: _summarize_metric_slice(results) for segment, results in segment_rows.items()
    }

    clarify_distribution = {
        "overall": _clarify_distribution(normalized),
        "friendly": _clarify_distribution(segment_rows["friendly"]),
        "regression": _clarify_distribution(segment_rows["regression"]),
        "adversarial": _clarify_distribution(segment_rows["adversarial"]),
    }

    return {
        "fixture_catalog_version": "v0.3",
        "fixture_count": len(fixtures),
        "required_fixture_ids": required_ids,
        "missing_required_fixture_ids": missing_fixture_ids,
        "fixture_groups": build_fixture_group_index(fixtures),
        "overall": overall,
        "segments": segment_summary,
        "silent_high_conflict_rate": overall["silent_high_conflict_rate"],
        "clarify_trigger_distribution": clarify_distribution,
    }


def build_fixture_group_index(
    fixtures: Sequence[BenchmarkFixture] = V0_3_BENCHMARK_FIXTURES,
) -> dict[str, list[str]]:
    groups: dict[str, list[str]] = {
        "friendly": [],
        "regression": [],
        "adversarial": [],
        "scale_evidence": [],
        "cross_cultural": [],
        "barcode_label_stub": [],
    }
    for fixture in fixtures:
        for group in fixture.groups:
            groups[group].append(fixture.fixture_id)
    return {name: sorted(values) for name, values in groups.items()}


def _normalize_result_row(
    row: Mapping[str, Any],
    fixture_index: Mapping[str, BenchmarkFixture],
) -> BenchmarkFixtureResult:
    fixture_id = _extract_fixture_id(row)
    fixture = fixture_index.get(fixture_id) if fixture_id is not None else None

    decision = _extract_decision(row)
    clarify_triggered = _extract_clarify_triggered(row, decision)
    high_conflict = _extract_high_conflict(row)
    silent_high_conflict = high_conflict and not clarify_triggered and not _is_block(decision)

    segment = _extract_segment(row, fixture)
    return BenchmarkFixtureResult(
        fixture_id=fixture_id,
        segment=segment,
        decision=decision,
        clarify_triggered=clarify_triggered,
        high_conflict=high_conflict,
        silent_high_conflict=silent_high_conflict,
        row=row,
    )


def _extract_fixture_id(row: Mapping[str, Any]) -> str | None:
    for key in ("fixture_id", "fixture", "id"):
        value = row.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _extract_segment(
    row: Mapping[str, Any],
    fixture: BenchmarkFixture | None,
) -> FixtureSegment | None:
    for key in ("segment", "fixture_segment", "fixture_group"):
        value = row.get(key)
        if not isinstance(value, str):
            continue
        normalized = value.strip().lower()
        if normalized in ("friendly", "regression", "adversarial"):
            return normalized  # type: ignore[return-value]
    return fixture.segment if fixture is not None else None


def _extract_decision(row: Mapping[str, Any]) -> str | None:
    for key in ("decision", "gate_decision", "review_state", "final_decision"):
        value = row.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip().upper()
    return None


def _extract_clarify_triggered(row: Mapping[str, Any], decision: str | None) -> bool:
    explicit = row.get("clarify_triggered")
    if isinstance(explicit, bool):
        return explicit
    if decision is not None:
        return decision == "CLARIFY"
    return False


def _extract_high_conflict(row: Mapping[str, Any]) -> bool:
    for key in (
        "high_conflict",
        "has_high_conflict",
        "high_conflict_detected",
        "silent_high_conflict",
    ):
        value = row.get(key)
        if isinstance(value, bool):
            return value

    severity_value = row.get("conflict_severity")
    if isinstance(severity_value, str) and severity_value.strip().lower() == "high":
        return True

    numeric_fields = ("high_conflict_count",)
    for key in numeric_fields:
        value = row.get(key)
        if isinstance(value, (int, float)) and value > 0:
            return True

    conflicts_value = row.get("conflicts")
    if isinstance(conflicts_value, Sequence):
        for conflict in conflicts_value:
            if not isinstance(conflict, Mapping):
                continue
            severity = conflict.get("severity")
            if isinstance(severity, str) and severity.strip().lower() == "high":
                return True
    return False


def _is_block(decision: str | None) -> bool:
    return decision == "BLOCK"


def _summarize_metric_slice(results: Sequence[BenchmarkFixtureResult]) -> dict[str, Any]:
    if not results:
        return {
            "rows": 0,
            "fixture_ids_seen": [],
            "coverage_rate": None,
            "mean_relative_range_width": None,
            "clarify_trigger_rate": None,
            "log_anyway_rate": None,
            "high_conflict_rate": None,
            "silent_high_conflict_rate": None,
            "decision_distribution": {},
        }

    decision_counter = Counter(
        result.decision if result.decision is not None else "UNKNOWN" for result in results
    )
    fixture_ids_seen = sorted(
        fixture_id
        for fixture_id in {result.fixture_id for result in results}
        if fixture_id is not None
    )
    high_conflict_count = sum(1 for result in results if result.high_conflict)
    silent_high_conflict_count = sum(1 for result in results if result.silent_high_conflict)

    return {
        "rows": len(results),
        "fixture_ids_seen": fixture_ids_seen,
        "coverage_rate": _mean_bool(
            result.row.get("correction_within_range") for result in results
        ),
        "mean_relative_range_width": _mean_number(
            result.row.get("relative_range_width") for result in results
        ),
        "clarify_trigger_rate": _mean_bool(result.clarify_triggered for result in results),
        "log_anyway_rate": _mean_bool(
            result.row.get("user_accepted_wide_range") for result in results
        ),
        "high_conflict_rate": _safe_rate(high_conflict_count, len(results)),
        "silent_high_conflict_rate": _safe_rate(silent_high_conflict_count, len(results)),
        "decision_distribution": dict(sorted(decision_counter.items())),
    }


def _clarify_distribution(results: Sequence[BenchmarkFixtureResult]) -> dict[str, Any]:
    total = len(results)
    triggered = sum(1 for result in results if result.clarify_triggered)
    not_triggered = total - triggered
    return {
        "rows": total,
        "triggered": triggered,
        "not_triggered": not_triggered,
        "trigger_rate": _safe_rate(triggered, total),
    }


def _mean_bool(values: Iterable[object]) -> float | None:
    bool_values = [bool(value) for value in values if value is not None]
    if not bool_values:
        return None
    return sum(1 for value in bool_values if value) / len(bool_values)


def _mean_number(values: Iterable[object]) -> float | None:
    numbers: list[float] = []
    for value in values:
        if value is None:
            continue
        try:
            numbers.append(float(value))
        except (TypeError, ValueError):
            continue
    if not numbers:
        return None
    return sum(numbers) / len(numbers)


def _safe_rate(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return numerator / denominator


__all__ = [
    "BenchmarkFixture",
    "BenchmarkFixtureResult",
    "FixtureFamily",
    "FixtureGroup",
    "FixtureSegment",
    "GateName",
    "V0_3_BENCHMARK_FIXTURES",
    "V0_3_REQUIRED_FIXTURE_IDS",
    "build_fixture_group_index",
    "load_fixture_results_jsonl",
    "summarize_benchmark_results",
]
