# Meal Component Mapping

`services.meal` turns vision output into deterministic local meal estimates.

## Public API

- `analyze_meal_components(components, candidate_limit=3, min_match_score=0.60, confident_match_score=0.70)`
- `estimate_meal_from_components(...)` as a compatibility alias
- `normalize_meal_components(...)`
- `NormalizedMealComponent`
- `NormalizedMealComponents`
- `NormalizedFoodCandidate`
- `NormalizedStateHint`
- `NormalizedHiddenIngredientRisk`
- `ComponentMatchCandidate`
- `MealComponentEstimate`
- `MealEstimate`

## Pipeline

- The input can be legacy `services.vision.FoodComponent` objects or a structured `services.vision.VisionAnalysisResponse`.
- `normalize_meal_components()` performs deterministic cleanup before nutrition matching:
  - trims whitespace
  - normalizes case for matching
  - merges obvious duplicate components
  - preserves source component ids and names
  - preserves top-k candidates, visual evidence, state hints, hidden ingredient risks, and meal uncertainty flags
- For each component, `parse_portion_range()` converts `portion_hint` into a conservative `PortionGramRange`.
- `match_food_name()` ranks local USDA and personal catalog entries.
- The top `candidate_limit` matches are retained in `top_candidates`.
- The highest-ranked candidate is selected only when its score meets `confident_match_score`.
- Matched components are converted to `FoodMacroInterval` with `calculate_food_macro_interval()`.
- Unmatched components stay in the result with `status="unmatched"` and an `unmatched_reason`.
- Meal totals are produced by `aggregate_meal_macro_interval()` using only matched components.

## Result Models

- `MealComponentEstimate` is a frozen Pydantic model with `extra="forbid"`.
- `MealEstimate` is a frozen Pydantic model with `extra="forbid"`.
- Both models are immutable and traceable.

`MealComponentEstimate` includes trace fields for:

- `component_name`
- `component_confidence`
- `portion_hint`
- `top_candidates`
- `selected_macro_entry_id`
- `selected_macro_entry_name`
- `selected_macro_entry_source`
- `selected_match_score`
- `portion_range`
- `macro_interval`
- `unmatched_reason`

Each `ComponentMatchCandidate` records:

- `macro_entry_id`
- `macro_entry_name`
- `macro_entry_source`
- `score`
- `matched_on`
- `match_type`

`MealEstimate` includes:

- `component_estimates`
- `matched_component_count`
- `unmatched_component_count`
- aggregated `macro_interval`

## Notes

- The local matcher prefers `PERSONAL` entries over `USDA` entries when scores are tied.
- The pipeline is deterministic and local; it does not call Claude, OpenAI, or any network service.
- For an end-to-end local demo that includes vision analysis and SQLite persistence, see [docs/cli.md](cli.md).

## Verification

- `pytest tests/meal/`
- `pytest tests/`
- `ruff check services/meal/ tests/meal/`
