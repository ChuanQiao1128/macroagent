from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal

from pydantic import Field

from services.meal.takeoff.evidence_arbitration import arbitrate_evidence_claims
from services.meal.takeoff.ledger_gate import apply_ledger_gate
from services.meal.takeoff.macro_quantity import aggregate_meal_macros, compute_component_macros
from services.meal.takeoff.schemas import (
    EvidenceClaim,
    MacroValueClaim,
    PortionRange,
    SourceMatchClaim,
    StrictModel,
)
from services.meal.takeoff.trace import InMemoryTraceEmitter, emit_stage_event
from services.storage.ledger import AppendOnlyLedger, LedgerEntry, LedgerVersionMatrix
from services.storage.trace_store import TraceStore

StageDecision = Literal["ACCEPT", "WARN", "CLARIFY", "BLOCK"]


class MealCase(StrictModel):
    fixture_id: str
    meal_id: str
    user_id: str
    trace_id: str
    component_id: str
    component_name: str
    quantity_min_g: float = Field(ge=0)
    quantity_best_g: float = Field(ge=0)
    quantity_max_g: float = Field(ge=0)
    kcal_per_100g: float = Field(gt=0)
    include_llm_raw_macro_claim: bool = False
    log_anyway: bool = False


class PipelineFixtureResult(StrictModel):
    fixture_id: str
    expected_decision: StageDecision
    decision: StageDecision
    contract_violation: bool
    trace_event_count: int
    ledger_written: bool
    ledger_entry: LedgerEntry | None


class IntegrationSmokeResult(StrictModel):
    fixtures: list[PipelineFixtureResult]


def run_integration_smoke_pipeline() -> IntegrationSmokeResult:
    version_matrix = LedgerVersionMatrix(
        calculator_version="macro_quantity_v0.3",
        uncertainty_policy_version="uncertainty_policy_v0.3",
        energy_density_policy_version="energy_density_policy_v0.3",
        scale_evidence_policy_version="scale_evidence_policy_v0.3",
        contract_yaml_version="contracts_v0.3",
        source_dataset_versions={"mock_usda": "2026-05-06"},
        takeoff_pipeline_version="integration_smoke_v0.1",
        semantic_judge_version="disabled_mock",
    )

    ledger = AppendOnlyLedger()

    fixtures: list[tuple[MealCase, StageDecision]] = [
        (
            MealCase(
                fixture_id="accept_fixture",
                meal_id="meal-accept",
                user_id="user-1",
                trace_id="trace-accept",
                component_id="comp-accept",
                component_name="rice",
                quantity_min_g=90,
                quantity_best_g=100,
                quantity_max_g=110,
                kcal_per_100g=160,
            ),
            "ACCEPT",
        ),
        (
            MealCase(
                fixture_id="warn_fixture",
                meal_id="meal-warn",
                user_id="user-1",
                trace_id="trace-warn",
                component_id="comp-warn",
                component_name="pasta",
                quantity_min_g=70,
                quantity_best_g=100,
                quantity_max_g=130,
                kcal_per_100g=150,
            ),
            "WARN",
        ),
        (
            MealCase(
                fixture_id="clarify_fixture",
                meal_id="meal-clarify",
                user_id="user-1",
                trace_id="trace-clarify",
                component_id="comp-clarify",
                component_name="stew",
                quantity_min_g=60,
                quantity_best_g=100,
                quantity_max_g=140,
                kcal_per_100g=120,
                log_anyway=True,
            ),
            "CLARIFY",
        ),
        (
            MealCase(
                fixture_id="block_fixture",
                meal_id="meal-block",
                user_id="user-1",
                trace_id="trace-block",
                component_id="comp-block",
                component_name="mystery_bowl",
                quantity_min_g=90,
                quantity_best_g=100,
                quantity_max_g=110,
                kcal_per_100g=170,
                include_llm_raw_macro_claim=True,
            ),
            "BLOCK",
        ),
    ]

    results = [
        _run_fixture(
            meal_case=meal_case,
            expected_decision=expected_decision,
            ledger=ledger,
            version_matrix=version_matrix,
        )
        for meal_case, expected_decision in fixtures
    ]

    return IntegrationSmokeResult(fixtures=results)


def _run_fixture(
    *,
    meal_case: MealCase,
    expected_decision: StageDecision,
    ledger: AppendOnlyLedger,
    version_matrix: LedgerVersionMatrix,
) -> PipelineFixtureResult:
    trace_store = TraceStore()
    emitter = InMemoryTraceEmitter()

    _emit(
        emitter,
        trace_store,
        meal_case,
        stage="MealCase",
        payload={"fixture_id": meal_case.fixture_id},
    )

    component_takeoff = {
        "component_id": meal_case.component_id,
        "component_name": meal_case.component_name,
    }
    _emit(
        emitter,
        trace_store,
        meal_case,
        stage="ComponentTakeoff",
        payload=component_takeoff,
    )

    source_seed_candidates = [
        {
            "source_ref": "mock:source:1",
            "source_name": "Mock USDA Seed",
            "source_type": "usda",
            "kcal_per_100g": meal_case.kcal_per_100g,
        }
    ]
    _emit(
        emitter,
        trace_store,
        meal_case,
        stage="SourceSeed",
        payload={"candidate_count": len(source_seed_candidates)},
    )

    source_critic_result = {
        "selected_source_ref": source_seed_candidates[0]["source_ref"],
        "nutrition_value_confidence": "high",
    }
    _emit(
        emitter,
        trace_store,
        meal_case,
        stage="SourceCritic",
        payload=source_critic_result,
    )

    scale_resolution = {
        "resolution_id": f"resolution:{meal_case.fixture_id}",
        "status": "confirmed",
        "scale_confidence": "high",
    }
    _emit(
        emitter,
        trace_store,
        meal_case,
        stage="ScaleEvidenceResolution",
        payload=scale_resolution,
    )

    portion_range = PortionRange(
        component_id=meal_case.component_id,
        quantity_unit="g",
        quantity_min=meal_case.quantity_min_g,
        quantity_best=meal_case.quantity_best_g,
        quantity_max=meal_case.quantity_max_g,
        primary_basis="reference_object_calibrated",
        scale_evidence_ids=["scale:mock-1"],
        confidence_label="high",
        confidence_score=0.92,
        uncertainty_drivers=["mock_scale"],
    )
    _emit(
        emitter,
        trace_store,
        meal_case,
        stage="PortionRange",
        payload=portion_range.model_dump(mode="json"),
    )

    component_estimate = compute_component_macros(
        source={
            "source_ref": source_critic_result["selected_source_ref"],
            "kcal_per_100g": meal_case.kcal_per_100g,
            "protein_g_per_100g": 5.0,
            "carbs_g_per_100g": 20.0,
            "fat_g_per_100g": 3.0,
        },
        portion_range=portion_range,
        component_id=meal_case.component_id,
        name=meal_case.component_name,
        category="mock",
        evidence_refs=["mock:portion"],
    )
    meal_estimate = aggregate_meal_macros([component_estimate], meal_id=meal_case.meal_id)
    _emit(
        emitter,
        trace_store,
        meal_case,
        stage="MacroQuantity",
        payload={
            "kcal_min": meal_estimate.kcal_min,
            "kcal_best": meal_estimate.kcal_best,
            "kcal_max": meal_estimate.kcal_max,
            "relative_range_width": meal_estimate.relative_range_width,
        },
    )

    evidence_claims = _build_mock_claims(meal_case, source_ref=source_seed_candidates[0]["source_ref"])
    arbitration = arbitrate_evidence_claims(evidence_claims)
    contract_violation = any(conflict.decision == "block_ledger_write" for conflict in arbitration.conflicts)
    _emit(
        emitter,
        trace_store,
        meal_case,
        stage="EvidenceArbitration",
        payload={
            "conflict_count": len(arbitration.conflicts),
            "contract_violation": contract_violation,
        },
    )

    gate = apply_ledger_gate(
        meal=meal_estimate,
        contract_violation=contract_violation,
        log_anyway=meal_case.log_anyway,
        user_decline_clarify_reason="trusts_estimate" if meal_case.log_anyway else None,
        ledger=ledger,
        version_matrix=version_matrix,
        meal_id=meal_case.meal_id,
        user_id=meal_case.user_id,
        trace_id=meal_case.trace_id,
        top_uncertainty_drivers=meal_estimate.top_uncertainty_drivers,
        meal_signature_hash=f"sig:{meal_case.fixture_id}",
    )
    _emit(
        emitter,
        trace_store,
        meal_case,
        stage="LedgerGate",
        payload=gate.model_dump(mode="json"),
        user_accepted_wide_range=gate.user_accepted_wide_range,
        user_decline_clarify_reason=gate.user_decline_clarify_reason,
    )

    ledger_entry: LedgerEntry | None = None
    if gate.decision != "BLOCK" and gate.should_write_ledger and gate.ledger_entry_id is None:
        ledger_entry = ledger.append_meal_estimate(
            version_matrix=version_matrix,
            meal_id=meal_case.meal_id,
            user_id=meal_case.user_id,
            trace_id=meal_case.trace_id,
            kcal_min=meal_estimate.kcal_min,
            kcal_best=meal_estimate.kcal_best,
            kcal_max=meal_estimate.kcal_max,
            protein_best=meal_estimate.protein_best,
            carbs_best=meal_estimate.carbs_best,
            fat_best=meal_estimate.fat_best,
            confidence_label=gate.confidence_label,
            top_uncertainty_drivers=meal_estimate.top_uncertainty_drivers,
            user_accepted_wide_range=gate.user_accepted_wide_range,
            user_decline_clarify_reason=gate.user_decline_clarify_reason,
            meal_signature_hash=f"sig:{meal_case.fixture_id}",
            entry_id=f"entry:{meal_case.fixture_id}",
        )
    elif gate.ledger_entry_id is not None:
        ledger_entry = ledger.get_entry(gate.ledger_entry_id)

    _emit(
        emitter,
        trace_store,
        meal_case,
        stage="TraceStore",
        payload={"event_count": len(emitter.events)},
        user_accepted_wide_range=gate.user_accepted_wide_range,
        user_decline_clarify_reason=gate.user_decline_clarify_reason,
    )

    _emit(
        emitter,
        trace_store,
        meal_case,
        stage="LedgerEntry",
        payload={
            "written": ledger_entry is not None,
            "entry_id": ledger_entry.entry_id if ledger_entry is not None else None,
        },
        user_accepted_wide_range=gate.user_accepted_wide_range,
        user_decline_clarify_reason=gate.user_decline_clarify_reason,
    )

    return PipelineFixtureResult(
        fixture_id=meal_case.fixture_id,
        expected_decision=expected_decision,
        decision=gate.decision,
        contract_violation=contract_violation,
        trace_event_count=len(trace_store.get_trace(meal_case.trace_id)),
        ledger_written=ledger_entry is not None,
        ledger_entry=ledger_entry,
    )


def _build_mock_claims(meal_case: MealCase, *, source_ref: str) -> list[EvidenceClaim]:
    claims: list[EvidenceClaim] = [
        EvidenceClaim(
            claim_id=f"claim:source:{meal_case.fixture_id}",
            source_type="nutrition_database",
            confidence_label="high",
            confidence_score=0.9,
            evidence_refs=["mock:db"],
            evidence_timestamp="2026-05-06T00:00:00Z",
            payload=SourceMatchClaim(
                claim_type="source_match",
                component_id=meal_case.component_id,
                source_ref=source_ref,
                source_name="Mock USDA",
                source_type="usda",
            ),
        )
    ]

    if meal_case.include_llm_raw_macro_claim:
        claims.append(
            EvidenceClaim(
                claim_id=f"claim:llm:{meal_case.fixture_id}",
                source_type="vision",
                confidence_label="medium",
                confidence_score=0.6,
                evidence_refs=["mock:llm"],
                evidence_timestamp="2026-05-06T00:00:00Z",
                payload=MacroValueClaim(
                    claim_type="macro_value",
                    component_id=meal_case.component_id,
                    kcal=200,
                    value_basis="llm_raw",
                ),
            )
        )

    return claims


def _emit(
    emitter: InMemoryTraceEmitter,
    trace_store: TraceStore,
    meal_case: MealCase,
    *,
    stage: str,
    payload: Mapping[str, Any],
    user_accepted_wide_range: bool | None = None,
    user_decline_clarify_reason: str | None = None,
) -> None:
    event = emit_stage_event(
        emitter,
        trace_id=meal_case.trace_id,
        stage=stage,
        event_name=f"{stage.lower()}.completed",
        meal_id=meal_case.meal_id,
        component_id=meal_case.component_id,
        user_accepted_wide_range=user_accepted_wide_range,
        user_decline_clarify_reason=user_decline_clarify_reason,
        payload=dict(payload),
    )
    trace_store.append(event)


__all__ = [
    "IntegrationSmokeResult",
    "MealCase",
    "PipelineFixtureResult",
    "run_integration_smoke_pipeline",
]
