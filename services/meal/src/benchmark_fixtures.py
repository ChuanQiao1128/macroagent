from __future__ import annotations

import json
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import yaml

from services.meal.takeoff.energy_density import run_energy_density_checks
from services.meal.takeoff.evidence_arbitration import arbitrate_evidence_claims
from services.meal.takeoff.schemas import (
    EvidenceClaim,
    MacroValueClaim,
    PortionQuantityClaim,
)

FixtureSegment = Literal["friendly", "regression", "adversarial"]
FixtureFamily = Literal["scale_evidence", "cross_cultural", "barcode_label_stub"]
GateName = Literal["scale_evidence", "energy_density", "evidence_arbitration"]
FixtureGroup = FixtureSegment | FixtureFamily

POLICY_DIR = Path(__file__).resolve().parents[1] / "policies"
DEFAULT_UNCERTAINTY_POLICY_PATH = POLICY_DIR / "uncertainty_policy.yaml"
DEFAULT_SCALE_EVIDENCE_POLICY_PATH = POLICY_DIR / "scale_evidence_policy.yaml"


@dataclass(frozen=True, slots=True)
class BenchmarkFixture:
    fixture_id: str
    title: str
    gate: GateName
    segment: FixtureSegment
    groups: tuple[FixtureGroup, ...]
    case: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class BenchmarkFixtureResult:
    fixture_id: str | None
    segment: FixtureSegment | None
    decision: str | None
    clarify_triggered: bool
    clarify_trigger_cause: str | None
    high_conflict: bool
    silent_high_conflict: bool
    row: Mapping[str, Any]


def _fixture(
    fixture_id: str,
    title: str,
    gate: GateName,
    segment: FixtureSegment,
    case: Mapping[str, Any],
    *families: FixtureFamily,
) -> BenchmarkFixture:
    return BenchmarkFixture(
        fixture_id=fixture_id,
        title=title,
        gate=gate,
        segment=segment,
        groups=(segment, *families),
        case=case,
    )


def _scale_case(
    *,
    kcal_min: float,
    kcal_best: float,
    kcal_max: float,
    correction_within_range: bool,
    user_accepted_wide_range: bool = False,
    high_conflict: bool = False,
    contract_violation: bool = False,
    clarify_trigger_cause: str | None = None,
) -> dict[str, Any]:
    return {
        "kcal_min": kcal_min,
        "kcal_best": kcal_best,
        "kcal_max": kcal_max,
        "correction_within_range": correction_within_range,
        "user_accepted_wide_range": user_accepted_wide_range,
        "high_conflict": high_conflict,
        "contract_violation": contract_violation,
        "clarify_trigger_cause": clarify_trigger_cause,
    }


def _energy_density_case(
    *,
    components: Sequence[Mapping[str, Any]],
    meal: Mapping[str, Any],
    correction_within_range: bool,
    relative_range_width: float,
    user_accepted_wide_range: bool = False,
    high_conflict: bool = False,
    clarify_trigger_cause: str | None = None,
) -> dict[str, Any]:
    return {
        "components": tuple(dict(component) for component in components),
        "meal": dict(meal),
        "correction_within_range": correction_within_range,
        "relative_range_width": relative_range_width,
        "user_accepted_wide_range": user_accepted_wide_range,
        "high_conflict": high_conflict,
        "clarify_trigger_cause": clarify_trigger_cause,
    }


def _evidence_case(
    *,
    claims: Sequence[EvidenceClaim],
    correction_within_range: bool,
    relative_range_width: float,
    user_accepted_wide_range: bool = False,
    clarify_trigger_cause: str | None = None,
) -> dict[str, Any]:
    return {
        "claims": tuple(claims),
        "correction_within_range": correction_within_range,
        "relative_range_width": relative_range_width,
        "user_accepted_wide_range": user_accepted_wide_range,
        "clarify_trigger_cause": clarify_trigger_cause,
    }


def _claim(
    claim_id: str,
    payload: MacroValueClaim | PortionQuantityClaim,
    *,
    source_type: str = "vision",
    confidence_label: str = "medium",
    confidence_score: float = 0.60,
) -> EvidenceClaim:
    return EvidenceClaim(
        claim_id=claim_id,
        source_type=source_type,
        confidence_label=confidence_label,
        confidence_score=confidence_score,
        evidence_refs=[f"evidence:{claim_id}"],
        evidence_timestamp="2026-05-05T00:00:00Z",
        payload=payload,
    )


V0_3_BENCHMARK_FIXTURES: tuple[BenchmarkFixture, ...] = (
    _fixture(
        "no_reference_low_impact",
        "No reference with low impact meal",
        "scale_evidence",
        "friendly",
        _scale_case(
            kcal_min=91.0,
            kcal_best=100.0,
            kcal_max=109.0,
            correction_within_range=True,
        ),
        "scale_evidence",
    ),
    _fixture(
        "no_reference_high_impact_bowl",
        "No reference with high-impact bowl",
        "scale_evidence",
        "adversarial",
        _scale_case(
            kcal_min=72.0,
            kcal_best=100.0,
            kcal_max=128.0,
            correction_within_range=False,
            high_conflict=True,
        ),
        "scale_evidence",
    ),
    _fixture(
        "spoon_visible_near_plate",
        "Spoon visible near plate",
        "scale_evidence",
        "friendly",
        _scale_case(
            kcal_min=89.0,
            kcal_best=100.0,
            kcal_max=111.0,
            correction_within_range=True,
        ),
        "scale_evidence",
    ),
    _fixture(
        "fork_visible_far_from_plate",
        "Fork visible far from plate",
        "scale_evidence",
        "regression",
        _scale_case(
            kcal_min=72.0,
            kcal_best=100.0,
            kcal_max=128.0,
            correction_within_range=True,
        ),
        "scale_evidence",
    ),
    _fixture(
        "saved_bowl_detected",
        "Saved bowl calibration detected",
        "scale_evidence",
        "friendly",
        _scale_case(
            kcal_min=90.0,
            kcal_best=100.0,
            kcal_max=110.0,
            correction_within_range=True,
        ),
        "scale_evidence",
    ),
    _fixture(
        "barcode_packaged_food",
        "Barcode for packaged food",
        "scale_evidence",
        "friendly",
        _scale_case(
            kcal_min=80.0,
            kcal_best=100.0,
            kcal_max=120.0,
            correction_within_range=True,
        ),
        "scale_evidence",
        "barcode_label_stub",
    ),
    _fixture(
        "card_like_object_with_pii",
        "Card-like object with PII should be rejected",
        "scale_evidence",
        "adversarial",
        _scale_case(
            kcal_min=81.0,
            kcal_best=100.0,
            kcal_max=119.0,
            correction_within_range=True,
            contract_violation=True,
        ),
        "scale_evidence",
        "barcode_label_stub",
    ),
    _fixture(
        "plate_visible_unknown_size",
        "Plate visible with unknown physical size",
        "scale_evidence",
        "regression",
        _scale_case(
            kcal_min=64.0,
            kcal_best=100.0,
            kcal_max=136.0,
            correction_within_range=False,
            clarify_trigger_cause="missing_scale",
        ),
        "scale_evidence",
    ),
    _fixture(
        "cooked_rice_correct_density",
        "Cooked rice uses cooked density",
        "energy_density",
        "friendly",
        _energy_density_case(
            components=[
                {
                    "component_id": "component-rice",
                    "category": "cooked_grain",
                    "kcal_best": 130.0,
                    "quantity_best": 100.0,
                }
            ],
            meal={
                "meal_id": "meal-cooked-rice",
                "meal_type": "plated_meal",
                "kcal_best": 130.0,
                "quantity_best": 100.0,
            },
            correction_within_range=True,
            relative_range_width=0.19,
        ),
        "cross_cultural",
    ),
    _fixture(
        "dry_rice_incorrectly_used_for_cooked_rice",
        "Dry rice density incorrectly used for cooked rice",
        "energy_density",
        "regression",
        _energy_density_case(
            components=[
                {
                    "component_id": "component-rice",
                    "category": "cooked_grain",
                    "kcal_best": 320.0,
                    "quantity_best": 100.0,
                }
            ],
            meal={
                "meal_id": "meal-dry-rice-error",
                "meal_type": "plated_meal",
                "kcal_best": 320.0,
                "quantity_best": 100.0,
            },
            correction_within_range=False,
            relative_range_width=0.67,
            user_accepted_wide_range=True,
            clarify_trigger_cause="density_outlier",
        ),
        "cross_cultural",
    ),
    _fixture(
        "sauce_mapped_to_oil",
        "Sauce mapped to oil density policy",
        "energy_density",
        "regression",
        _energy_density_case(
            components=[
                {
                    "component_id": "component-sauce",
                    "category": "oil_pure",
                    "kcal_best": 700.0,
                    "quantity_best": 100.0,
                }
            ],
            meal={
                "meal_id": "meal-oil-sauce",
                "meal_type": "fried_meal",
                "kcal_best": 500.0,
                "quantity_best": 100.0,
            },
            correction_within_range=True,
            relative_range_width=0.49,
        ),
        "cross_cultural",
    ),
    _fixture(
        "mixed_bowl_aggregate_passes_component_fails",
        "Mixed bowl aggregate passes but a component fails",
        "energy_density",
        "adversarial",
        _energy_density_case(
            components=[
                {
                    "component_id": "component-rice",
                    "category": "cooked_grain",
                    "kcal_best": 210.0,
                    "quantity_best": 100.0,
                },
                {
                    "component_id": "component-chicken",
                    "category": "lean_meat",
                    "kcal_best": 170.0,
                    "quantity_best": 100.0,
                },
            ],
            meal={
                "meal_id": "meal-mixed-component-fail",
                "meal_type": "mixed_bowl",
                "kcal_best": 640.0,
                "quantity_best": 100.0,
            },
            correction_within_range=False,
            relative_range_width=0.74,
            high_conflict=True,
        ),
        "cross_cultural",
    ),
    _fixture(
        "compatible_portion_ranges_merge",
        "Compatible portion ranges merge",
        "evidence_arbitration",
        "friendly",
        _evidence_case(
            claims=[
                _claim(
                    "portion-vision",
                    PortionQuantityClaim(
                        claim_type="portion_quantity",
                        component_id="component-rice",
                        quantity_min=160.0,
                        quantity_best=190.0,
                        quantity_max=220.0,
                        quantity_unit="g",
                    ),
                    source_type="vision",
                    confidence_score=0.58,
                ),
                _claim(
                    "portion-container",
                    PortionQuantityClaim(
                        claim_type="portion_quantity",
                        component_id="component-rice",
                        quantity_min=180.0,
                        quantity_best=205.0,
                        quantity_max=230.0,
                        quantity_unit="g",
                    ),
                    source_type="personal_prior",
                    confidence_score=0.75,
                ),
            ],
            correction_within_range=True,
            relative_range_width=0.28,
        ),
        "cross_cultural",
    ),
    _fixture(
        "incompatible_macro_values_conflict",
        "Incompatible macro values conflict",
        "evidence_arbitration",
        "regression",
        _evidence_case(
            claims=[
                _claim(
                    "macro-database",
                    MacroValueClaim(
                        claim_type="macro_value",
                        component_id="component-rice",
                        kcal=100.0,
                        value_basis="database_source",
                    ),
                    source_type="nutrition_database",
                ),
                _claim(
                    "macro-recompute",
                    MacroValueClaim(
                        claim_type="macro_value",
                        component_id="component-rice",
                        kcal=170.0,
                        value_basis="deterministic_recompute",
                    ),
                    source_type="deterministic_calculator",
                ),
            ],
            correction_within_range=False,
            relative_range_width=0.63,
            clarify_trigger_cause="macro_conflict",
        ),
        "cross_cultural",
    ),
    _fixture(
        "user_correction_beats_default_prior",
        "User correction beats default prior",
        "evidence_arbitration",
        "friendly",
        _evidence_case(
            claims=[
                _claim(
                    "portion-user-correction",
                    PortionQuantityClaim(
                        claim_type="portion_quantity",
                        component_id="component-noodles",
                        quantity_min=220.0,
                        quantity_best=240.0,
                        quantity_max=260.0,
                        quantity_unit="g",
                    ),
                    source_type="user_correction",
                    confidence_label="high",
                    confidence_score=0.95,
                ),
                _claim(
                    "portion-personal-prior",
                    PortionQuantityClaim(
                        claim_type="portion_quantity",
                        component_id="component-noodles",
                        quantity_min=210.0,
                        quantity_best=235.0,
                        quantity_max=270.0,
                        quantity_unit="g",
                    ),
                    source_type="personal_prior",
                    confidence_score=0.70,
                ),
            ],
            correction_within_range=True,
            relative_range_width=0.24,
        ),
        "cross_cultural",
    ),
    _fixture(
        "llm_raw_macro_blocks",
        "LLM raw macro claim is blocked by arbitration",
        "evidence_arbitration",
        "adversarial",
        _evidence_case(
            claims=[
                _claim(
                    "macro-llm-raw",
                    MacroValueClaim(
                        claim_type="macro_value",
                        component_id="component-1",
                        kcal=500.0,
                        value_basis="llm_raw",
                    ),
                    source_type="vision",
                    confidence_label="low",
                    confidence_score=0.20,
                )
            ],
            correction_within_range=True,
            relative_range_width=0.31,
        ),
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


def generate_executable_fixture_results(
    fixtures: Sequence[BenchmarkFixture] = V0_3_BENCHMARK_FIXTURES,
) -> list[dict[str, Any]]:
    return [run_executable_fixture(fixture) for fixture in fixtures]


def run_executable_fixture(fixture: BenchmarkFixture) -> dict[str, Any]:
    if fixture.gate == "scale_evidence":
        return _run_scale_evidence_fixture(fixture)
    if fixture.gate == "energy_density":
        return _run_energy_density_fixture(fixture)
    if fixture.gate == "evidence_arbitration":
        return _run_evidence_arbitration_fixture(fixture)
    raise ValueError(f"unsupported benchmark fixture gate: {fixture.gate}")


def summarize_benchmark_results(
    rows: Sequence[Mapping[str, Any]],
    fixtures: Sequence[BenchmarkFixture] = V0_3_BENCHMARK_FIXTURES,
) -> dict[str, Any]:
    if not _llm_raw_macro_block_rule_is_enforced():
        raise ValueError("evidence arbitration policy must block llm_raw macro claims")

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
    clarify_triggered = _extract_clarify_triggered(
        row,
        decision,
        gate=fixture.gate if fixture is not None else None,
    )
    high_conflict = _extract_high_conflict(row)
    clarify_trigger_cause = _extract_clarify_trigger_cause(
        row,
        decision,
        clarify_triggered,
        fixture=fixture,
        high_conflict=high_conflict,
    )
    silent_high_conflict = high_conflict and not clarify_triggered and not _is_block(decision)

    segment = _extract_segment(row, fixture)
    return BenchmarkFixtureResult(
        fixture_id=fixture_id,
        segment=segment,
        decision=decision,
        clarify_triggered=clarify_triggered,
        clarify_trigger_cause=clarify_trigger_cause,
        high_conflict=high_conflict,
        silent_high_conflict=silent_high_conflict,
        row=row,
    )


def _run_scale_evidence_fixture(fixture: BenchmarkFixture) -> dict[str, Any]:
    from services.meal.takeoff.ledger_gate import apply_ledger_gate

    case = fixture.case
    result = apply_ledger_gate(
        kcal_min=float(case["kcal_min"]),
        kcal_best=float(case["kcal_best"]),
        kcal_max=float(case["kcal_max"]),
        contract_violation=bool(case.get("contract_violation", False)),
        log_anyway=bool(case.get("user_accepted_wide_range", False)),
        user_decline_clarify_reason=(
            "no_reference_available"
            if bool(case.get("user_accepted_wide_range", False))
            else None
        ),
    )
    row = _base_executable_result_row(fixture)
    row.update(
        {
            "decision": result.decision,
            "correction_within_range": bool(case["correction_within_range"]),
            "relative_range_width": result.relative_range_width,
            "user_accepted_wide_range": bool(case.get("user_accepted_wide_range", False)),
            "high_conflict": bool(case.get("high_conflict", False)),
        }
    )
    _maybe_add_clarify_cause(row, case, result.decision)
    return row


def _run_energy_density_fixture(fixture: BenchmarkFixture) -> dict[str, Any]:
    case = fixture.case
    audit = run_energy_density_checks(
        components=case["components"],
        meal=case["meal"],
    )
    row = _base_executable_result_row(fixture)
    row.update(
        {
            "decision": audit.overall_decision,
            "correction_within_range": bool(case["correction_within_range"]),
            "relative_range_width": float(case["relative_range_width"]),
            "user_accepted_wide_range": bool(case.get("user_accepted_wide_range", False)),
            "high_conflict": bool(case.get("high_conflict", False)),
        }
    )
    _maybe_add_clarify_cause(row, case, audit.overall_decision)
    return row


def _run_evidence_arbitration_fixture(fixture: BenchmarkFixture) -> dict[str, Any]:
    case = fixture.case
    arbitration = arbitrate_evidence_claims(case["claims"])
    decision = _arbitration_decision(arbitration.conflicts)
    high_conflict = any(conflict.severity == "high" for conflict in arbitration.conflicts)

    row = _base_executable_result_row(fixture)
    row.update(
        {
            "decision": decision,
            "correction_within_range": bool(case["correction_within_range"]),
            "relative_range_width": float(case["relative_range_width"]),
            "user_accepted_wide_range": bool(case.get("user_accepted_wide_range", False)),
            "high_conflict": high_conflict,
        }
    )
    _maybe_add_clarify_cause(row, case, decision)
    return row


def _base_executable_result_row(fixture: BenchmarkFixture) -> dict[str, Any]:
    return {
        "fixture_id": fixture.fixture_id,
        "gate": fixture.gate,
        "segment": fixture.segment,
    }


def _maybe_add_clarify_cause(
    row: dict[str, Any],
    case: Mapping[str, Any],
    decision: str,
) -> None:
    if decision != "CLARIFY":
        return
    cause = case.get("clarify_trigger_cause")
    if isinstance(cause, str) and cause.strip():
        row["clarify_trigger_cause"] = cause.strip().lower()


def _arbitration_decision(conflicts: Sequence[Any]) -> str:
    if any(conflict.decision == "block_ledger_write" for conflict in conflicts):
        return "BLOCK"
    if conflicts:
        return "CLARIFY"
    return "ACCEPT"


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


def _extract_clarify_triggered(
    row: Mapping[str, Any],
    decision: str | None,
    *,
    gate: GateName | None,
) -> bool:
    explicit = row.get("clarify_triggered")
    if isinstance(explicit, bool):
        return explicit
    if _is_block(decision):
        return False
    if decision is not None:
        return decision == "CLARIFY"

    relative_range_width = _extract_relative_range_width(row)
    policy_threshold = _clarify_relative_width_threshold(gate=gate)
    if relative_range_width is not None and policy_threshold is not None:
        return relative_range_width > policy_threshold

    return False


def _extract_clarify_trigger_cause(
    row: Mapping[str, Any],
    decision: str | None,
    clarify_triggered: bool,
    *,
    fixture: BenchmarkFixture | None,
    high_conflict: bool,
) -> str | None:
    for key in ("clarify_trigger_cause", "clarify_cause", "trigger_cause"):
        value = row.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip().lower() if clarify_triggered else None

    if not clarify_triggered:
        return None

    if fixture is not None:
        if fixture.gate == "scale_evidence":
            return "missing_scale"
        if fixture.gate == "energy_density":
            return "density_outlier"
        if fixture.gate == "evidence_arbitration":
            return "macro_conflict" if high_conflict else "evidence_conflict"

    if decision == "CLARIFY":
        return "range_width"
    return "unknown"


def _extract_relative_range_width(row: Mapping[str, Any]) -> float | None:
    value = row.get("relative_range_width")
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _clarify_relative_width_threshold(
    *,
    gate: GateName | None,
) -> float | None:
    default_threshold = _load_uncertainty_warn_relative_width_max()
    if gate != "scale_evidence":
        return default_threshold
    scale_evidence_threshold = _load_scale_evidence_missing_scale_threshold()
    if scale_evidence_threshold is not None:
        return scale_evidence_threshold
    return default_threshold


@lru_cache(maxsize=1)
def _load_uncertainty_warn_relative_width_max() -> float | None:
    policy = _load_yaml_mapping(DEFAULT_UNCERTAINTY_POLICY_PATH)
    range_decision = policy.get("range_decision")
    if not isinstance(range_decision, Mapping):
        return None
    return _coerce_float(range_decision.get("warn_relative_width_max"))


@lru_cache(maxsize=1)
def _load_scale_evidence_missing_scale_threshold() -> float | None:
    policy = _load_yaml_mapping(DEFAULT_SCALE_EVIDENCE_POLICY_PATH)
    missing_scale = policy.get("missing_scale")
    if not isinstance(missing_scale, Mapping):
        return None
    return _coerce_float(missing_scale.get("clarify_if_relative_range_width_gt"))


def _load_yaml_mapping(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as file_obj:
        loaded = yaml.safe_load(file_obj)
    if not isinstance(loaded, dict):
        return {}
    return loaded


def _coerce_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


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


@lru_cache(maxsize=1)
def _llm_raw_macro_block_rule_is_enforced() -> bool:
    claim = EvidenceClaim(
        claim_id="benchmark:llm-raw",
        source_type="vision",
        confidence_label="low",
        confidence_score=0.20,
        evidence_refs=["evidence:benchmark:llm-raw"],
        evidence_timestamp="2026-05-05T00:00:00Z",
        payload=MacroValueClaim(
            claim_type="macro_value",
            component_id="component-1",
            kcal=500.0,
            value_basis="llm_raw",
        ),
    )
    result = arbitrate_evidence_claims([claim])
    return any(
        conflict.claim_type == "macro_value"
        and conflict.metric == "value_basis"
        and conflict.metric_value == "llm_raw"
        and conflict.decision == "block_ledger_write"
        for conflict in result.conflicts
    )


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
    cause_counter = Counter(
        result.clarify_trigger_cause or "unknown"
        for result in results
        if result.clarify_triggered
    )
    return {
        "rows": total,
        "triggered": triggered,
        "not_triggered": not_triggered,
        "trigger_rate": _safe_rate(triggered, total),
        "by_cause": dict(sorted(cause_counter.items())),
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
    "generate_executable_fixture_results",
    "load_fixture_results_jsonl",
    "run_executable_fixture",
    "summarize_benchmark_results",
]
