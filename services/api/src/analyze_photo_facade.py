from __future__ import annotations

from dataclasses import dataclass

from services.accounting import PortionGramBounds, calculate_food_macro_interval
from services.api.src.schemas import (
    AnalyzePhotoFacadeRequest,
    AnalyzePhotoFacadeResponse,
    ClarifyQuestion,
    NutritionInterval,
    NutritionIntervals,
    UncertaintySummary,
)
from services.capture import build_sanitized_capture_trace_artifact, resolve_scale_evidence_from_capture
from services.meal.src.api_integration import build_default_ledger_version_matrix
from services.meal.takeoff.evidence_arbitration import arbitrate_evidence_claims
from services.meal.takeoff.ledger_gate import apply_ledger_gate
from services.meal.takeoff.schemas import EvidenceClaim, MacroValueClaim, PortionQuantityClaim
from services.meal.takeoff.trace import InMemoryTraceEmitter, emit_stage_event
from services.nutrition import match_food_name, parse_portion_range
from services.storage.ledger import AppendOnlyLedger


@dataclass(frozen=True, slots=True)
class _MockComponent:
    name: str
    portion_hint: str
    source_query: str


_FIXTURE_COMPONENTS: dict[str, _MockComponent] = {
    "accept": _MockComponent(
        name="white rice",
        portion_hint="100 g",
        source_query="cooked white rice",
    ),
    "warn": _MockComponent(
        name="chicken breast",
        portion_hint="1 cup",
        source_query="grilled chicken breast",
    ),
    "clarify": _MockComponent(
        name="mixed salad",
        portion_hint="some amount",
        source_query="broccoli",
    ),
    "block": _MockComponent(name="pasta", portion_hint="100 g", source_query="cooked pasta"),
}
_WARN_FIXTURE_GRAM_MULTIPLIER_MIN = 0.75
_WARN_FIXTURE_GRAM_MULTIPLIER_MAX = 1.25


def analyze_photo_facade(
    request: AnalyzePhotoFacadeRequest,
    *,
    ledger: AppendOnlyLedger | None = None,
) -> AnalyzePhotoFacadeResponse:
    payload = request.payload
    fixture_id = _fixture_id_from_request_id(payload.request_id)
    trace_id = f"trace:{payload.request_id}"
    emitter = InMemoryTraceEmitter()

    scale = resolve_scale_evidence_from_capture(
        trace_id=trace_id,
        capture_metadata=payload.capture_metadata,
        emitter=emitter,
        image_sha256=payload.image_identity.image_sha256,
    )
    scale_resolution = scale.resolutions[0]

    capture_trace_artifact = build_sanitized_capture_trace_artifact(
        request=payload,
        scale_evidence=scale,
        model_version=None,
        prompt_version=None,
        barcode_marked_safe=payload.capture_metadata.barcode_payload_safe,
    )

    emit_stage_event(
        emitter,
        trace_id=trace_id,
        stage="AnalyzePhotoFacade",
        event_name="capture.trace_artifact_built",
        image_sha256=payload.image_identity.image_sha256,
        payload=capture_trace_artifact,
    )

    component = _FIXTURE_COMPONENTS[fixture_id]
    portion = parse_portion_range(
        component_name=component.name,
        portion_hint=component.portion_hint,
    )
    matches = match_food_name(component.source_query)
    if not matches:
        raise ValueError(f"no deterministic nutrition match for query {component.source_query!r}")
    entry = matches[0].entry

    emit_stage_event(
        emitter,
        trace_id=trace_id,
        stage="AnalyzePhotoFacade",
        event_name="capture.portion_parsed",
        image_sha256=payload.image_identity.image_sha256,
        payload={
            "component_name": component.name,
            "portion_hint": component.portion_hint,
            "portion_source": portion.source,
        },
    )

    portion_bounds = PortionGramBounds(
        grams_min=portion.grams_min,
        grams_max=portion.grams_max,
        grams_p10=portion.grams_p10,
        grams_p50=portion.grams_p50,
        grams_p90=portion.grams_p90,
        percentiles_available=True,
    )
    if fixture_id == "warn":
        warn_grams_min = portion.grams_p50 * _WARN_FIXTURE_GRAM_MULTIPLIER_MIN
        warn_grams_max = portion.grams_p50 * _WARN_FIXTURE_GRAM_MULTIPLIER_MAX
        portion_bounds = PortionGramBounds(
            grams_min=warn_grams_min,
            grams_max=warn_grams_max,
            grams_p10=warn_grams_min,
            grams_p50=portion.grams_p50,
            grams_p90=warn_grams_max,
            percentiles_available=True,
        )

    meal_interval = calculate_food_macro_interval(entry, portion_bounds)

    claims = _build_claims(
        fixture_id=fixture_id,
        trace_id=trace_id,
        component_name=component.name,
        portion=portion,
        meal_interval=meal_interval,
        scale_evidence_id=scale_resolution.selected_candidate_id,
    )
    arbitration = arbitrate_evidence_claims(claims)
    has_blocking_conflict = any(
        conflict.decision == "block_ledger_write" for conflict in arbitration.conflicts
    )

    gate = apply_ledger_gate(
        kcal_min=meal_interval.kcal.min,
        kcal_best=meal_interval.kcal.p50,
        kcal_max=meal_interval.kcal.max,
        contract_violation=has_blocking_conflict,
        log_anyway=request.options.log_anyway,
        user_decline_clarify_reason=request.options.log_anyway_reason,
        ledger=ledger,
        version_matrix=build_default_ledger_version_matrix() if ledger is not None else None,
        meal_id=f"meal:{payload.request_id}",
        user_id=payload.user_id,
        trace_id=trace_id,
        entry_id=f"entry:{payload.request_id}",
        top_uncertainty_drivers=[*portion.uncertainty_flags],
        meal_signature_hash=f"sig:{payload.image_identity.image_sha256[:16]}",
    )

    if gate.decision == "BLOCK":
        reasons = [
            "unsupported raw macro claim from llm"
            if has_blocking_conflict
            else gate.decision_reason
        ]
        return AnalyzePhotoFacadeResponse(
            request_id=payload.request_id,
            status="BLOCK",
            nutrition=None,
            reasons=reasons,
            clarify_questions=[],
            trace_id=trace_id,
            ledger_entry_id=None,
            uncertainty_summary=UncertaintySummary(
                confidence_label="low",
                relative_range_width=gate.relative_range_width,
                uncertainty_flags=["blocked_input"],
            ),
        )

    status = gate.decision
    reasons = [gate.decision_reason]
    clarify_questions: list[ClarifyQuestion] = []

    if status == "CLARIFY":
        clarify_questions = [
            ClarifyQuestion(
                question_id="clarify_portion_reference",
                text="Could you add a known-size reference object or confirm the portion size?",
            ),
            ClarifyQuestion(
                question_id="clarify_component_identity",
                text="Please confirm the main component and any hidden sauces/oils.",
            ),
        ]

    if status == "WARN" and scale_resolution.scale_confidence in {"low", "none"}:
        reasons.append("scale confidence is low; interval may be wide")

    uncertainty_flags = [*portion.uncertainty_flags]
    if status == "WARN" and not uncertainty_flags:
        uncertainty_flags.append("wide_portion_range")

    return AnalyzePhotoFacadeResponse(
        request_id=payload.request_id,
        status=status,
        nutrition=_to_nutrition_intervals(
            meal_interval=meal_interval,
            source_ref=entry.id,
        ),
        reasons=reasons,
        clarify_questions=clarify_questions,
        trace_id=trace_id,
        ledger_entry_id=gate.ledger_entry_id,
        uncertainty_summary=UncertaintySummary(
            confidence_label=gate.confidence_label,
            relative_range_width=gate.relative_range_width,
            uncertainty_flags=uncertainty_flags,
        ),
    )


def _fixture_id_from_request_id(request_id: str) -> str:
    key = request_id.strip().lower()
    for fixture in ("accept", "warn", "clarify", "block"):
        if fixture in key:
            return fixture
    return "accept"


def _build_claims(
    *,
    fixture_id: str,
    trace_id: str,
    component_name: str,
    portion,
    meal_interval,
    scale_evidence_id: str | None,
) -> list[EvidenceClaim]:
    evidence_refs = [scale_evidence_id] if scale_evidence_id is not None else []
    claims: list[EvidenceClaim] = [
        EvidenceClaim(
            claim_id=f"claim:portion:{fixture_id}",
            source_type="vision",
            confidence_label="medium",
            confidence_score=0.78,
            evidence_refs=evidence_refs,
            evidence_timestamp="2026-05-06T00:00:00+00:00",
            payload=PortionQuantityClaim(
                claim_type="portion_quantity",
                component_id=f"component:{component_name}",
                quantity_min=portion.grams_min,
                quantity_best=portion.grams_p50,
                quantity_max=portion.grams_max,
                quantity_unit="g",
            ),
        ),
        EvidenceClaim(
            claim_id=f"claim:macro:det:{fixture_id}",
            source_type="deterministic_calculator",
            confidence_label="high",
            confidence_score=0.92,
            evidence_refs=evidence_refs,
            evidence_timestamp="2026-05-06T00:00:01+00:00",
            payload=MacroValueClaim(
                claim_type="macro_value",
                component_id=f"component:{component_name}",
                kcal=meal_interval.kcal.p50,
                protein_g=meal_interval.protein_g.p50,
                carbs_g=meal_interval.carbs_g.p50,
                fat_g=meal_interval.fat_g.p50,
                value_basis="deterministic_recompute",
            ),
        ),
    ]

    if fixture_id == "block":
        claims.append(
            EvidenceClaim(
                claim_id=f"claim:macro:llm:{fixture_id}",
                source_type="vision",
                confidence_label="low",
                confidence_score=0.55,
                evidence_refs=[*evidence_refs, trace_id],
                evidence_timestamp="2026-05-06T00:00:02+00:00",
                payload=MacroValueClaim(
                    claim_type="macro_value",
                    component_id=f"component:{component_name}",
                    kcal=max(1.0, meal_interval.kcal.p50 - 35.0),
                    protein_g=meal_interval.protein_g.p50,
                    carbs_g=meal_interval.carbs_g.p50,
                    fat_g=meal_interval.fat_g.p50,
                    value_basis="llm_raw",
                ),
            )
        )

    return claims


def _to_nutrition_intervals(
    *,
    meal_interval,
    source_ref: str,
) -> NutritionIntervals:
    source = f"deterministic:{source_ref}"

    def _interval(metric) -> NutritionInterval:
        return NutritionInterval(
            best_estimate=metric.p50,
            min_estimate=metric.min,
            max_estimate=metric.max,
            source=source,
        )

    return NutritionIntervals(
        kcal=NutritionInterval(
            best_estimate=meal_interval.kcal.p50,
            min_estimate=meal_interval.kcal.min,
            max_estimate=meal_interval.kcal.max,
            source=source,
        ),
        protein_g=_interval(meal_interval.protein_g),
        carbs_g=_interval(meal_interval.carbs_g),
        fat_g=_interval(meal_interval.fat_g),
        sugar_g=_interval(meal_interval.sugar_g),
        sodium_mg=_interval(meal_interval.sodium_mg),
        fiber_g=_interval(meal_interval.fiber_g),
    )


__all__ = ["analyze_photo_facade"]
