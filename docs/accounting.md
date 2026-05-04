# Nutrition Interval Calculator

`services.accounting` provides deterministic nutrition interval and best-estimate calculators for turning a `NutritionEntry` and a gram range into meal-level nutrition outputs.

## Public API

The package exports:

- `PortionGramBounds`
- `MacroRange`
- `MacroSourceTrace`
- `FoodMacroInterval`
- `MealMacroInterval`
- `MacroBestEstimate`
- `MacroBestEstimateSet`
- `calculate_food_macro_interval(entry, gram_range)`
- `calculate_macro_interval(entry, gram_range)` as a compatibility alias
- `aggregate_meal_macro_interval(food_intervals)`
- `calculate_meal_macro_interval(items)`
- `calculate_macro_best_estimate(macro_range)`
- `calculate_food_macro_best_estimate(food_interval)`
- `calculate_meal_macro_best_estimate(meal_interval)`

## Models

All public interval models are frozen Pydantic models:

- `MacroRange` stores a `min` and `max` value for one nutrient metric.
- `MacroSourceTrace` records the `NutritionEntry` identity and the gram bounds used to compute the interval.
- `FoodMacroInterval` stores the per-food ranges for `kcal`, `protein_g`, `carbs_g`, `fat_g`, `sugar_g`, `sodium_mg`, and `fiber_g`.
- `MealMacroInterval` stores the aggregated meal ranges, the ordered food items, and their source traces.
- `MacroBestEstimate` stores a deterministic single-value estimate plus the estimation method used.
- `MacroBestEstimateSet` stores per-metric best estimates for `kcal`, `protein_g`, `carbs_g`, `fat_g`, `sugar_g`, `sodium_mg`, and `fiber_g`.

## Behavior

- The calculator uses only the per-100g values on `NutritionEntry`.
- It accepts either `services.nutrition.PortionGramRange` or `PortionGramBounds`.
- It rejects negative gram bounds and rejects ranges where `grams_min > grams_max`.
- It rounds all nutrition outputs to one decimal place using half-up rounding.
- Meal aggregation sums the per-food `min` values and the per-food `max` values, then rounds the totals to one decimal place.
- Best-estimate selection is deterministic and local.
- For positive metric ranges, best estimates use the geometric midpoint, `sqrt(min * max)`.
- If either bound is zero, best estimates fall back to the arithmetic midpoint, `(min + max) / 2`.
- Equal positive bounds remain unchanged and are reported with `method="geometric_midpoint"`.

## Verification

- `pytest tests/accounting/test_macro_interval.py`
- `pytest tests/accounting/test_macro_best_estimate.py`
- `ruff check services/`
