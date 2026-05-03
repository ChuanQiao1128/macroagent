# Macro Interval Calculator

`services.accounting` provides a deterministic macro calculator for turning a `MacroEntry` and a gram range into macro intervals.

## Public API

The package exports:

- `PortionGramBounds`
- `MacroRange`
- `MacroSourceTrace`
- `FoodMacroInterval`
- `MealMacroInterval`
- `calculate_food_macro_interval(entry, gram_range)`
- `calculate_macro_interval(entry, gram_range)` as a compatibility alias
- `aggregate_meal_macro_interval(food_intervals)`
- `calculate_meal_macro_interval(items)`

## Models

All public interval models are frozen Pydantic models:

- `MacroRange` stores a `min` and `max` value for one macro.
- `MacroSourceTrace` records the `MacroEntry` identity and the gram bounds used to compute the interval.
- `FoodMacroInterval` stores the per-food ranges for `kcal`, `protein_g`, `carbs_g`, and `fat_g`.
- `MealMacroInterval` stores the aggregated meal ranges, the ordered food items, and their source traces.

## Behavior

- The calculator uses only the per-100g values on `MacroEntry`.
- It accepts either `services.nutrition.PortionGramRange` or `PortionGramBounds`.
- It rejects negative gram bounds and rejects ranges where `grams_min > grams_max`.
- It rounds all macro outputs to one decimal place using half-up rounding.
- Meal aggregation sums the per-food `min` values and the per-food `max` values, then rounds the totals to one decimal place.

## Verification

- `pytest tests/accounting/test_macro_interval.py`
- `ruff check services/`
