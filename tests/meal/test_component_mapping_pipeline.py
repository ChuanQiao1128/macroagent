from __future__ import annotations

import pytest
from pydantic import ValidationError

from services.meal import analyze_meal_components, estimate_meal_from_components
from services.trace import build_trace_version_metadata
from services.vision import (
    FoodCandidate,
    FoodComponent,
    HiddenIngredientRisk,
    PortionEstimate,
    StructuredFoodComponent,
    VisionAnalysisResponse,
)


def test_analyze_meal_components_returns_matched_component_with_trace_fields() -> None:
    meal = analyze_meal_components(
        [
            FoodComponent(
                name="white rice",
                confidence=0.91,
                portion_hint="100 g",
            )
        ]
    )

    assert meal.matched_component_count == 1
    assert meal.unmatched_component_count == 0
    assert len(meal.component_estimates) == 1

    component = meal.component_estimates[0]
    assert component.component_name == "white rice"
    assert component.component_confidence == pytest.approx(0.91)
    assert component.status == "matched"
    assert component.selected_macro_entry_id == "usda_seed_0001"
    assert component.selected_macro_entry_name == "White rice, cooked"
    assert component.selected_macro_entry_source == "USDA"
    assert component.selected_match_score == pytest.approx(0.99)
    assert component.top_candidates[0].macro_entry_id == "usda_seed_0001"
    assert component.top_candidates[0].score == pytest.approx(0.99)

    assert component.portion_range.grams_min == 90.0
    assert component.portion_range.grams_max == 110.0
    assert component.portion_range.source == "portion_hint_weight_unit"

    assert component.macro_interval is not None
    assert component.macro_interval.kcal.min == 117.0
    assert component.macro_interval.kcal.max == 143.0
    assert component.macro_interval.protein_g.min == 2.2
    assert component.macro_interval.protein_g.max == 2.6
    assert component.macro_interval.carbs_g.min == 25.4
    assert component.macro_interval.carbs_g.max == 31.0
    assert component.macro_interval.fat_g.min == 0.3
    assert component.macro_interval.fat_g.max == 0.3


def test_analyze_meal_components_marks_low_confidence_candidate_as_unmatched() -> None:
    meal = analyze_meal_components(
        [FoodComponent(name="brocoli", confidence=0.80, portion_hint="1 cup")],
        confident_match_score=0.80,
    )

    assert meal.matched_component_count == 0
    assert meal.unmatched_component_count == 1

    component = meal.component_estimates[0]
    assert component.component_name == "brocoli"
    assert component.status == "unmatched"
    assert component.top_candidates[0].macro_entry_id == "usda_seed_0048"
    assert component.top_candidates[0].score == pytest.approx(0.7466666667)
    assert "below confident_match_score=0.80" in (component.unmatched_reason or "")
    assert component.selected_macro_entry_id is None
    assert component.selected_macro_entry_source is None
    assert component.selected_match_score is None
    assert component.macro_interval is None

    assert meal.macro_interval.items == ()
    assert meal.macro_interval.source_traces == ()
    assert meal.macro_interval.kcal.min == 0.0
    assert meal.macro_interval.kcal.max == 0.0
    assert meal.macro_interval.protein_g.min == 0.0
    assert meal.macro_interval.protein_g.max == 0.0
    assert meal.macro_interval.carbs_g.min == 0.0
    assert meal.macro_interval.carbs_g.max == 0.0
    assert meal.macro_interval.fat_g.min == 0.0
    assert meal.macro_interval.fat_g.max == 0.0


def test_analyze_meal_components_prefers_personal_entry_when_scores_tie() -> None:
    meal = analyze_meal_components(
        [FoodComponent(name="banana", confidence=0.93, portion_hint="half cup")],
        candidate_limit=2,
    )

    component = meal.component_estimates[0]
    assert component.status == "matched"
    assert len(component.top_candidates) == 2
    assert component.top_candidates[0].score == pytest.approx(component.top_candidates[1].score)
    assert component.top_candidates[0].macro_entry_source == "PERSONAL"
    assert component.top_candidates[1].macro_entry_source == "USDA"
    assert component.selected_macro_entry_id == "personal_seed_0012"
    assert component.selected_macro_entry_source == "PERSONAL"
    assert component.selected_match_score == pytest.approx(0.99)
    assert component.macro_interval is not None
    assert component.macro_interval.source_trace.macro_entry_id == "personal_seed_0012"
    assert component.macro_interval.source_trace.macro_entry_source == "PERSONAL"


def test_analyze_meal_components_aggregates_only_matched_components() -> None:
    meal = analyze_meal_components(
        [
            FoodComponent(name="banana", confidence=0.93, portion_hint="half cup"),
            FoodComponent(name="white rice", confidence=0.91, portion_hint="100 g"),
            FoodComponent(name="mystery foam", confidence=0.55, portion_hint="some amount"),
        ]
    )

    assert len(meal.component_estimates) == 3
    assert meal.matched_component_count == 2
    assert meal.unmatched_component_count == 1
    assert len(meal.macro_interval.items) == 2
    assert [trace.macro_entry_id for trace in meal.macro_interval.source_traces] == [
        "personal_seed_0012",
        "usda_seed_0001",
    ]

    assert meal.macro_interval.kcal.min == 170.4
    assert meal.macro_interval.kcal.max == 258.7
    assert meal.macro_interval.protein_g.min == 2.9
    assert meal.macro_interval.protein_g.max == 4.0
    assert meal.macro_interval.carbs_g.min == 39.1
    assert meal.macro_interval.carbs_g.max == 60.6
    assert meal.macro_interval.fat_g.min == 0.5
    assert meal.macro_interval.fat_g.max == 0.7

    unmatched = meal.component_estimates[2]
    assert unmatched.status == "unmatched"
    assert unmatched.unmatched_reason == "no food match candidate met min_match_score=0.60"


def test_estimate_meal_from_components_alias_matches_primary_and_returns_immutable_models() -> None:
    components = [FoodComponent(name="banana", confidence=0.93, portion_hint="half cup")]
    primary = analyze_meal_components(components)
    alias = estimate_meal_from_components(components)

    assert alias == primary

    with pytest.raises(ValidationError):
        alias.matched_component_count = 2

    with pytest.raises(ValidationError):
        alias.component_estimates[0].status = "unmatched"


def test_analyze_meal_components_uses_top_k_vision_candidate_fallback_with_reason_trace() -> None:
    response = VisionAnalysisResponse(
        components=[
            StructuredFoodComponent(
                component_id="comp-1",
                visible_name="mystery bowl",
                candidates=[
                    FoodCandidate(
                        name="mystery foam",
                        confidence=0.95,
                        visual_evidence=["blurry texture"],
                    ),
                    FoodCandidate(
                        name="banana",
                        confidence=0.72,
                        visual_evidence=["yellow fruit"],
                    ),
                ],
                portion=PortionEstimate(
                    description="100 g",
                    confidence=0.81,
                    visual_basis=["plate size"],
                ),
            )
        ]
    )

    meal = analyze_meal_components(response, candidate_limit=2)

    assert meal.matched_component_count == 1
    assert meal.unmatched_component_count == 0
    component = meal.component_estimates[0]

    assert component.component_name == "mystery foam"
    assert component.status == "matched"
    assert component.selected_macro_entry_id == "personal_seed_0012"
    assert len(component.top_candidates) == 2
    assert component.top_candidates[0].matched_on == "banana"
    assert (
        "matched via vision candidate 'banana' (confidence=0.72)"
        in component.top_candidates[0].reason
    )
    for candidate in component.top_candidates:
        assert candidate.macro_entry_source in {"USDA", "PERSONAL"}
        assert 0.0 <= candidate.score <= 1.0
        assert candidate.match_type in {
            "exact_name",
            "exact_alias",
            "token_containment",
            "fuzzy",
        }
        assert candidate.matched_on
        assert candidate.reason


def test_analyze_meal_components_preserves_trace_versions_from_structured_input() -> None:
    trace_versions = build_trace_version_metadata(
        vision_model_name="trace-meal-model",
        vision_prompt_text="trace meal prompt",
    )
    response = VisionAnalysisResponse(
        components=[
            StructuredFoodComponent(
                component_id="comp-1",
                visible_name="white rice",
                candidates=[
                    FoodCandidate(
                        name="white rice",
                        confidence=0.94,
                        visual_evidence=["white grains"],
                    )
                ],
                portion=PortionEstimate(
                    description="100 g",
                    confidence=0.81,
                    visual_basis=["plate scale"],
                ),
            )
        ],
        trace_versions=trace_versions,
    )

    meal = analyze_meal_components(response)

    assert meal.trace_versions == trace_versions
    assert meal.trace_versions.vision_model_name == "trace-meal-model"


def test_analyze_meal_components_flags_low_impact_unmatched_vegetable() -> None:
    meal = analyze_meal_components(
        [FoodComponent(name="brocoli", confidence=0.80, portion_hint="1 cup")],
        confident_match_score=0.80,
    )

    assert meal.estimate_status == "incomplete_low_impact"
    assert meal.macro_range_label == "known_components_only"
    assert meal.unmatched_component_count == 1
    assert meal.recommended_user_question is None

    signal = meal.uncertainty_signals[0]
    assert signal.source == "unmatched_component"
    assert signal.impact == "low"
    assert signal.estimated_kcal_delta == 0.0
    assert signal.estimated_fat_g_delta == 0.0
    assert signal.recommended_question is None

    component = meal.component_estimates[0]
    assert component.status == "unmatched"
    assert "below confident_match_score=0.80" in (component.unmatched_reason or "")


def test_analyze_meal_components_flags_high_impact_unmatched_sauce() -> None:
    meal = analyze_meal_components(
        [
            FoodComponent(
                name="mystery creamy sauce drizzle",
                confidence=0.65,
                portion_hint="1 cup",
            )
        ],
        confident_match_score=1.0,
    )

    assert meal.estimate_status == "incomplete_high_impact"
    assert meal.macro_range_label == "known_components_only"
    assert meal.unmatched_component_count == 1

    signal = meal.uncertainty_signals[0]
    assert signal.source == "unmatched_component"
    assert signal.impact == "high"
    assert "potential high-impact category detected: creamy_or_oily_sauce" in signal.reason
    assert signal.estimated_kcal_delta >= 40.0
    assert signal.estimated_fat_g_delta >= 4.0
    assert signal.recommended_question is not None
    assert "creamy or oily sauce" in signal.recommended_question
    assert meal.recommended_user_question == signal.recommended_question


def test_analyze_meal_components_flags_high_impact_unmatched_nut_butter() -> None:
    meal = analyze_meal_components(
        [FoodComponent(name="mystery peanut butter swirl", confidence=0.62, portion_hint="100 g")],
        confident_match_score=1.0,
    )

    assert meal.estimate_status == "incomplete_high_impact"
    assert meal.macro_range_label == "known_components_only"
    assert meal.unmatched_component_count == 1

    signal = meal.uncertainty_signals[0]
    assert signal.source == "unmatched_component"
    assert signal.impact == "high"
    assert "potential high-impact category detected: nuts_or_nut_butter" in signal.reason
    assert signal.estimated_kcal_delta >= 40.0
    assert signal.estimated_fat_g_delta >= 4.0
    assert signal.recommended_question is not None
    assert "nuts or nut butter" in signal.recommended_question
    assert meal.recommended_user_question == signal.recommended_question


def test_analyze_meal_components_flags_high_impact_unmatched_sugary_drink_or_dessert() -> None:
    meal = analyze_meal_components(
        [FoodComponent(name="mystery sweet tea", confidence=0.68, portion_hint="100 g")],
        confident_match_score=1.0,
    )

    assert meal.estimate_status == "incomplete_high_impact"
    assert meal.macro_range_label == "known_components_only"
    assert meal.unmatched_component_count == 1

    signal = meal.uncertainty_signals[0]
    assert signal.source == "unmatched_component"
    assert signal.impact == "high"
    assert "potential high-impact category detected: sugary_drink_or_dessert" in signal.reason
    assert signal.estimated_kcal_delta >= 40.0
    assert signal.recommended_question is not None
    assert "sugary drink or dessert" in signal.recommended_question
    assert meal.recommended_user_question == signal.recommended_question


def test_analyze_meal_components_flags_hidden_oil_risk_as_high_impact() -> None:
    response = VisionAnalysisResponse(
        components=[
            StructuredFoodComponent(
                component_id="comp-1",
                visible_name="White Rice",
                candidates=[
                    FoodCandidate(
                        name="white rice",
                        confidence=0.94,
                        visual_evidence=["rice grains"],
                    )
                ],
                portion=PortionEstimate(
                    description="100 g",
                    confidence=0.82,
                    visual_basis=["plate scale"],
                ),
                hidden_ingredient_risks=[
                    HiddenIngredientRisk(
                        ingredient="oil",
                        likelihood=0.78,
                        macro_impact="high",
                        rationale="oily sheen",
                    )
                ],
            )
        ]
    )

    meal = analyze_meal_components(response)

    assert meal.matched_component_count == 1
    assert meal.unmatched_component_count == 0
    assert meal.estimate_status == "incomplete_high_impact"
    assert meal.macro_range_label == "known_components_only"

    signal = meal.uncertainty_signals[0]
    assert signal.source == "hidden_ingredient_risk"
    assert signal.impact == "high"
    assert "hidden ingredient risk detected: oil" in signal.reason
    assert "evidence: oily sheen" in signal.reason
    assert signal.recommended_question == (
        "For white rice, was there hidden oil? About how much was used?"
    )
    assert meal.recommended_user_question == signal.recommended_question


def test_analyze_meal_components_labels_known_components_only_when_uncertainty_exists() -> None:
    complete = analyze_meal_components(
        [FoodComponent(name="white rice", confidence=0.91, portion_hint="100 g")]
    )
    assert complete.estimate_status == "complete"
    assert complete.macro_range_label == "full_meal"

    incomplete = analyze_meal_components(
        [
            FoodComponent(name="banana", confidence=0.93, portion_hint="half cup"),
            FoodComponent(name="mystery foam", confidence=0.55, portion_hint="some amount"),
        ]
    )
    assert incomplete.estimate_status == "incomplete_low_impact"
    assert incomplete.macro_range_label == "known_components_only"
    assert len(incomplete.macro_interval.items) == 1
    assert incomplete.macro_interval.items[0].source_trace.macro_entry_id == "personal_seed_0012"


def test_analyze_meal_components_selects_recommended_question_for_dominant_uncertainty() -> None:
    meal = analyze_meal_components(
        [
            FoodComponent(name="mystery oil drizzle", confidence=0.25, portion_hint="1 cup"),
            FoodComponent(name="mystery cheese topping", confidence=0.95, portion_hint="1 cup"),
        ],
        confident_match_score=1.0,
    )

    high_impact_signals = sorted(
        [signal for signal in meal.uncertainty_signals if signal.impact == "high"],
        key=lambda signal: signal.impact_score,
        reverse=True,
    )

    assert meal.estimate_status == "incomplete_high_impact"
    assert len(high_impact_signals) >= 2
    assert high_impact_signals[0].component_name == "mystery oil drizzle"
    assert high_impact_signals[0].impact_score >= high_impact_signals[1].impact_score * 1.35
    assert meal.recommended_user_question == high_impact_signals[0].recommended_question
    assert meal.recommended_user_question is not None
    assert "oil or butter" in meal.recommended_user_question
