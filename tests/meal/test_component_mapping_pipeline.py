from __future__ import annotations

import pytest
from pydantic import ValidationError

from services.meal import analyze_meal_components, estimate_meal_from_components
from services.vision import FoodComponent


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
