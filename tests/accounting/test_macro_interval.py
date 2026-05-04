from __future__ import annotations

import pytest
from pydantic import ValidationError

from services.accounting import (
    PortionGramBounds,
    aggregate_meal_macro_interval,
    calculate_food_macro_interval,
    calculate_macro_interval,
    calculate_meal_macro_interval,
)
from services.nutrition import MacroEntry, PortionGramRange


def _build_entry(
    *,
    entry_id: str,
    name: str,
    source: str,
    kcal_per_100g: float,
    protein_g_per_100g: float,
    carbs_g_per_100g: float,
    fat_g_per_100g: float,
    sugar_g_per_100g: float = 0.0,
    sodium_mg_per_100g: float = 0.0,
    fiber_g_per_100g: float = 0.0,
) -> MacroEntry:
    return MacroEntry(
        id=entry_id,
        name=name,
        aliases=(),
        category="test",
        source=source,
        kcal_per_100g=kcal_per_100g,
        protein_g_per_100g=protein_g_per_100g,
        carbs_g_per_100g=carbs_g_per_100g,
        fat_g_per_100g=fat_g_per_100g,
        sugar_g_per_100g=sugar_g_per_100g,
        sodium_mg_per_100g=sodium_mg_per_100g,
        fiber_g_per_100g=fiber_g_per_100g,
    )


def test_calculate_food_macro_interval_single_food_and_source_trace() -> None:
    entry = _build_entry(
        entry_id="seed_chicken",
        name="Chicken Breast",
        source="USDA",
        kcal_per_100g=165.0,
        protein_g_per_100g=31.0,
        carbs_g_per_100g=0.0,
        fat_g_per_100g=3.6,
        sugar_g_per_100g=2.0,
        sodium_mg_per_100g=74.0,
        fiber_g_per_100g=1.5,
    )
    gram_range = PortionGramBounds(grams_min=75.0, grams_max=125.0)

    interval = calculate_food_macro_interval(entry=entry, gram_range=gram_range)

    assert interval.kcal.min == 123.8
    assert interval.kcal.max == 206.3
    assert interval.protein_g.min == 23.3
    assert interval.protein_g.max == 38.8
    assert interval.carbs_g.min == 0.0
    assert interval.carbs_g.max == 0.0
    assert interval.fat_g.min == 2.7
    assert interval.fat_g.max == 4.5
    assert interval.sugar_g.min == 1.5
    assert interval.sugar_g.max == 2.5
    assert interval.sodium_mg.min == 55.5
    assert interval.sodium_mg.max == 92.5
    assert interval.fiber_g.min == 1.1
    assert interval.fiber_g.max == 1.9

    assert interval.source_trace.macro_entry_id == "seed_chicken"
    assert interval.source_trace.macro_entry_name == "Chicken Breast"
    assert interval.source_trace.macro_entry_source == "USDA"
    assert interval.source_trace.grams_min == 75.0
    assert interval.source_trace.grams_max == 125.0



def test_calculate_macro_interval_alias_matches_primary_function() -> None:
    entry = _build_entry(
        entry_id="seed_oats",
        name="Oats",
        source="PERSONAL",
        kcal_per_100g=389.0,
        protein_g_per_100g=16.9,
        carbs_g_per_100g=66.3,
        fat_g_per_100g=6.9,
    )
    gram_range = PortionGramBounds(grams_min=10.0, grams_max=40.0)

    primary = calculate_food_macro_interval(entry=entry, gram_range=gram_range)
    alias = calculate_macro_interval(entry=entry, gram_range=gram_range)

    assert alias == primary



def test_calculate_meal_macro_interval_aggregates_items_and_source_traces() -> None:
    chicken = _build_entry(
        entry_id="seed_chicken",
        name="Chicken Breast",
        source="USDA",
        kcal_per_100g=165.0,
        protein_g_per_100g=31.0,
        carbs_g_per_100g=0.0,
        fat_g_per_100g=3.6,
    )
    banana = _build_entry(
        entry_id="seed_banana",
        name="Banana",
        source="PERSONAL",
        kcal_per_100g=89.0,
        protein_g_per_100g=1.1,
        carbs_g_per_100g=22.8,
        fat_g_per_100g=0.3,
        sugar_g_per_100g=12.2,
        sodium_mg_per_100g=1.0,
        fiber_g_per_100g=2.6,
    )

    meal = calculate_meal_macro_interval(
        items=(
            (chicken, PortionGramBounds(grams_min=100.0, grams_max=120.0)),
            (banana, PortionGramBounds(grams_min=50.0, grams_max=150.0)),
        )
    )

    assert meal.kcal.min == 209.5
    assert meal.kcal.max == 331.5
    assert meal.protein_g.min == 31.6
    assert meal.protein_g.max == 38.9
    assert meal.carbs_g.min == 11.4
    assert meal.carbs_g.max == 34.2
    assert meal.fat_g.min == 3.8
    assert meal.fat_g.max == 4.8
    assert meal.sugar_g.min == 6.1
    assert meal.sugar_g.max == 18.3
    assert meal.sodium_mg.min == 0.5
    assert meal.sodium_mg.max == 1.5
    assert meal.fiber_g.min == 1.3
    assert meal.fiber_g.max == 3.9

    assert len(meal.items) == 2
    assert [trace.macro_entry_id for trace in meal.source_traces] == [
        "seed_chicken",
        "seed_banana",
    ]
    assert [trace.macro_entry_source for trace in meal.source_traces] == ["USDA", "PERSONAL"]



def test_aggregate_meal_macro_interval_accepts_precomputed_food_intervals() -> None:
    chicken = _build_entry(
        entry_id="seed_chicken",
        name="Chicken Breast",
        source="USDA",
        kcal_per_100g=165.0,
        protein_g_per_100g=31.0,
        carbs_g_per_100g=0.0,
        fat_g_per_100g=3.6,
    )
    rice = _build_entry(
        entry_id="seed_rice",
        name="Rice",
        source="USDA",
        kcal_per_100g=130.0,
        protein_g_per_100g=2.4,
        carbs_g_per_100g=28.0,
        fat_g_per_100g=0.3,
    )

    chicken_interval = calculate_food_macro_interval(
        entry=chicken,
        gram_range=PortionGramBounds(grams_min=80.0, grams_max=120.0),
    )
    rice_interval = calculate_food_macro_interval(
        entry=rice,
        gram_range=PortionGramBounds(grams_min=100.0, grams_max=100.0),
    )

    meal = aggregate_meal_macro_interval((chicken_interval, rice_interval))

    assert meal.kcal.min == 262.0
    assert meal.kcal.max == 328.0
    assert meal.protein_g.min == 27.2
    assert meal.protein_g.max == 39.6
    assert meal.carbs_g.min == 28.0
    assert meal.carbs_g.max == 28.0
    assert meal.fat_g.min == 3.2
    assert meal.fat_g.max == 4.6



def test_zero_gram_range_produces_zero_macros() -> None:
    entry = _build_entry(
        entry_id="seed_oil",
        name="Olive Oil",
        source="USDA",
        kcal_per_100g=884.0,
        protein_g_per_100g=0.0,
        carbs_g_per_100g=0.0,
        fat_g_per_100g=100.0,
    )

    interval = calculate_food_macro_interval(
        entry=entry,
        gram_range=PortionGramBounds(grams_min=0.0, grams_max=0.0),
    )

    assert interval.kcal.min == 0.0
    assert interval.kcal.max == 0.0
    assert interval.protein_g.min == 0.0
    assert interval.protein_g.max == 0.0
    assert interval.carbs_g.min == 0.0
    assert interval.carbs_g.max == 0.0
    assert interval.fat_g.min == 0.0
    assert interval.fat_g.max == 0.0



def test_calculator_accepts_portion_gram_range_input_type() -> None:
    entry = _build_entry(
        entry_id="seed_tofu",
        name="Tofu",
        source="PERSONAL",
        kcal_per_100g=76.0,
        protein_g_per_100g=8.0,
        carbs_g_per_100g=1.9,
        fat_g_per_100g=4.8,
    )
    gram_range = PortionGramRange(
        grams_min=90.0,
        grams_max=110.0,
        confidence=0.8,
        source="portion_hint_weight_unit",
        reason="parsed from hint",
    )

    interval = calculate_food_macro_interval(entry=entry, gram_range=gram_range)

    assert interval.kcal.min == 68.4
    assert interval.kcal.max == 83.6
    assert interval.protein_g.min == 7.2
    assert interval.protein_g.max == 8.8
    assert interval.carbs_g.min == 1.7
    assert interval.carbs_g.max == 2.1
    assert interval.fat_g.min == 4.3
    assert interval.fat_g.max == 5.3



def test_invalid_gram_ranges_are_rejected() -> None:
    with pytest.raises(ValidationError):
        PortionGramBounds(grams_min=50.0, grams_max=49.9)

    with pytest.raises(ValidationError):
        PortionGramBounds(grams_min=-0.1, grams_max=10.0)

    with pytest.raises(ValidationError):
        PortionGramBounds(grams_p10=90.0, grams_p50=80.0, grams_p90=100.0)

    with pytest.raises(ValidationError):
        PortionGramRange(
            grams_min=20.0,
            grams_max=10.0,
            confidence=0.8,
            source="portion_hint_weight_unit",
            reason="invalid",
        )


def test_rounding_is_consistent_to_one_decimal_place() -> None:
    entry = _build_entry(
        entry_id="seed_rounding",
        name="Rounding Fixture",
        source="USDA",
        kcal_per_100g=0.5,
        protein_g_per_100g=2.5,
        carbs_g_per_100g=5.0,
        fat_g_per_100g=7.5,
    )

    interval = calculate_food_macro_interval(
        entry=entry,
        gram_range=PortionGramBounds(grams_min=10.0, grams_max=30.0),
    )

    assert interval.kcal.min == 0.1
    assert interval.kcal.max == 0.2
    assert interval.protein_g.min == 0.3
    assert interval.protein_g.max == 0.8
    assert interval.carbs_g.min == 0.5
    assert interval.carbs_g.max == 1.5
    assert interval.fat_g.min == 0.8
    assert interval.fat_g.max == 2.3


def test_interval_models_are_immutable() -> None:
    entry = _build_entry(
        entry_id="seed_egg",
        name="Egg",
        source="USDA",
        kcal_per_100g=143.0,
        protein_g_per_100g=12.6,
        carbs_g_per_100g=0.7,
        fat_g_per_100g=9.5,
    )

    food_interval = calculate_food_macro_interval(
        entry=entry,
        gram_range=PortionGramBounds(grams_min=50.0, grams_max=60.0),
    )
    meal_interval = calculate_meal_macro_interval(
        items=((entry, PortionGramBounds(grams_min=50.0, grams_max=60.0)),)
    )

    with pytest.raises(ValidationError):
        food_interval.kcal = food_interval.kcal

    with pytest.raises(ValidationError):
        meal_interval.kcal = meal_interval.kcal
