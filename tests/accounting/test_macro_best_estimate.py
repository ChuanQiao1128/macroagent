from __future__ import annotations

import pytest
from pydantic import ValidationError

from services.accounting import (
    MacroRange,
    PortionGramBounds,
    calculate_food_macro_best_estimate,
    calculate_food_macro_interval,
    calculate_macro_best_estimate,
    calculate_meal_macro_best_estimate,
    calculate_meal_macro_interval,
)
from services.nutrition import MacroEntry


def _build_entry(
    *,
    entry_id: str,
    name: str,
    source: str,
    kcal_per_100g: float,
    protein_g_per_100g: float,
    carbs_g_per_100g: float,
    fat_g_per_100g: float,
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
    )


def test_calculate_macro_best_estimate_uses_geometric_midpoint_for_positive_range() -> None:
    estimate = calculate_macro_best_estimate(MacroRange(min=4.0, max=9.0))

    assert estimate.value == 6.0
    assert estimate.method == "geometric_midpoint"


@pytest.mark.parametrize(
    ("min_value", "max_value", "expected_value"),
    (
        (0.0, 10.0, 5.0),
        (0.0, 0.0, 0.0),
    ),
)
def test_calculate_macro_best_estimate_uses_arithmetic_midpoint_for_zero_inclusive_ranges(
    min_value: float,
    max_value: float,
    expected_value: float,
) -> None:
    estimate = calculate_macro_best_estimate(MacroRange(min=min_value, max=max_value))

    assert estimate.value == expected_value
    assert estimate.method == "arithmetic_midpoint"


def test_calculate_macro_best_estimate_equal_positive_bounds_are_deterministic() -> None:
    estimate = calculate_macro_best_estimate(MacroRange(min=15.0, max=15.0))

    assert estimate.value == 15.0
    assert estimate.method == "geometric_midpoint"


def test_calculate_macro_best_estimate_uses_p50_when_percentiles_are_available() -> None:
    estimate = calculate_macro_best_estimate(
        MacroRange(
            min=10.0,
            max=30.0,
            p10=10.0,
            p50=12.3,
            p90=30.0,
            percentiles_available=True,
        )
    )

    assert estimate.value == 12.3
    assert estimate.method == "percentile_p50"


def test_calculate_macro_best_estimate_rejects_invalid_ranges() -> None:
    with pytest.raises(ValidationError):
        MacroRange(min=9.1, max=9.0)

    with pytest.raises(ValidationError):
        MacroRange(min=-0.1, max=3.0)

    with pytest.raises(ValidationError):
        MacroRange(min=5.0, max=10.0, p10=5.0, p50=11.0, p90=10.0)


def test_calculate_food_macro_best_estimate_preserves_all_macro_fields() -> None:
    chicken = _build_entry(
        entry_id="seed_chicken",
        name="Chicken Breast",
        source="USDA",
        kcal_per_100g=165.0,
        protein_g_per_100g=31.0,
        carbs_g_per_100g=0.0,
        fat_g_per_100g=3.6,
    )
    interval = calculate_food_macro_interval(
        entry=chicken,
        gram_range=PortionGramBounds(grams_min=75.0, grams_max=125.0),
    )

    estimate = calculate_food_macro_best_estimate(interval)

    assert estimate.kcal.value == 159.8
    assert estimate.kcal.method == "geometric_midpoint"
    assert estimate.protein_g.value == 30.1
    assert estimate.protein_g.method == "geometric_midpoint"
    assert estimate.carbs_g.value == 0.0
    assert estimate.carbs_g.method == "arithmetic_midpoint"
    assert estimate.fat_g.value == 3.5
    assert estimate.fat_g.method == "geometric_midpoint"


def test_calculate_food_macro_best_estimate_uses_p50_when_source_interval_has_percentiles() -> None:
    tofu = _build_entry(
        entry_id="seed_tofu",
        name="Tofu",
        source="PERSONAL",
        kcal_per_100g=100.0,
        protein_g_per_100g=20.0,
        carbs_g_per_100g=30.0,
        fat_g_per_100g=40.0,
    )
    interval = calculate_food_macro_interval(
        entry=tofu,
        gram_range=PortionGramBounds(
            grams_p10=50.0,
            grams_p50=70.0,
            grams_p90=110.0,
            percentiles_available=True,
        ),
    )

    estimate = calculate_food_macro_best_estimate(interval)

    assert estimate.kcal.value == 70.0
    assert estimate.kcal.method == "percentile_p50"
    assert estimate.protein_g.value == 14.0
    assert estimate.protein_g.method == "percentile_p50"
    assert estimate.carbs_g.value == 21.0
    assert estimate.carbs_g.method == "percentile_p50"
    assert estimate.fat_g.value == 28.0
    assert estimate.fat_g.method == "percentile_p50"


def test_calculate_meal_macro_best_estimate_from_aggregate_interval() -> None:
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
    )

    meal_interval = calculate_meal_macro_interval(
        items=(
            (chicken, PortionGramBounds(grams_min=100.0, grams_max=120.0)),
            (banana, PortionGramBounds(grams_min=50.0, grams_max=150.0)),
        )
    )

    meal_estimate = calculate_meal_macro_best_estimate(meal_interval)

    assert meal_estimate.kcal.value == 263.5
    assert meal_estimate.kcal.method == "geometric_midpoint"
    assert meal_estimate.protein_g.value == 35.1
    assert meal_estimate.protein_g.method == "geometric_midpoint"
    assert meal_estimate.carbs_g.value == 19.7
    assert meal_estimate.carbs_g.method == "geometric_midpoint"
    assert meal_estimate.fat_g.value == 4.3
    assert meal_estimate.fat_g.method == "geometric_midpoint"
