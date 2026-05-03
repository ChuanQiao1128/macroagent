# Seed Nutrition Catalog

`services.nutrition` provides local seed nutrition catalogs used by Track A to map food names to macro entries without requiring a database or network access.

## Data Store

- USDA seed data lives in `services/nutrition/data/usda_seed.json`.
- Personal seed data lives in `services/nutrition/data/personal_seed.json`.
- Both catalogs are JSON-backed and inspectable in source control.
- The USDA seed set covers the broad generic catalog used for exact lookup.
- The personal seed set contains 20 commonly used foods, including branded milk, protein powder, yogurt, eggs, coffee, oats, rice, chicken, tuna, tofu, fruit, nuts, and cooking oil.

## Entry Model

The public model is `MacroEntry`, a frozen Pydantic model with stable fields:

- `id`
- `name`
- `aliases`
- `category`
- `source`
- `kcal_per_100g`
- `protein_g_per_100g`
- `carbs_g_per_100g`
- `fat_g_per_100g`

`MacroEntry.source` accepts either `USDA` or `PERSONAL`.

## Match Result Model

The ranked matcher returns `MacroMatchCandidate`, a frozen Pydantic model with:

- `entry`
- `score`
- `matched_on`
- `match_type`

`match_type` can be one of:

- `exact_name`
- `exact_alias`
- `token_containment`
- `fuzzy`

## Lookup API

The module exports these helpers:

- `load_macro_entries()`
- `load_personal_macro_entries()`
- `load_all_macro_entries()`
- `get_macro_entry(name_or_alias)`
- `get_macro_entry_by_name(name_or_alias)`
- `find_macro_entry(name_or_alias)`
- `match_food_name(query, limit=5, min_score=0.6)`
- `find_macro_entry_candidates(query, limit=5, min_score=0.6)`

Loader behavior:

- `load_macro_entries()` returns the USDA catalog.
- `load_personal_macro_entries()` returns the personal seed catalog.
- `load_all_macro_entries()` returns USDA and personal entries together.

Ranked matcher behavior:

- `match_food_name()` searches USDA and personal entries together.
- It supports exact name matches, exact alias matches, token containment, and lightweight fuzzy matching.
- Results are ranked by score, then personal entries are preferred over USDA entries when scores tie.
- `find_macro_entry_candidates()` is an alias for `match_food_name()` for call-site readability.

Exact lookup behavior remains exact-match only:

- case-insensitive
- whitespace-normalized
- matches against the entry `name` and its `aliases`
- does not do fuzzy matching

`get_macro_entry()`, `get_macro_entry_by_name()`, and `find_macro_entry()` continue to resolve against the USDA catalog only.

The loader returns an immutable tuple of frozen `MacroEntry` instances, so callers cannot mutate the cached catalog.

## Portion Parser

`services.nutrition` also exports a deterministic portion parser for converting common portion hints into conservative gram ranges.

Public API:

- `PortionGramRange`
- `parse_portion_range(component_name, portion_hint=None)`
- `parse_component_portion_range(component_name, portion_hint=None)` as a compatibility alias

Model fields:

- `grams_min`
- `grams_max`
- `confidence`
- `source`
- `reason`

Supported hint families:

- weight units: `g`, `gram`, `kg`, `kilogram`
- household units: `cup`, `bowl`, `plate`, `slice`, `piece`, `egg`, `scoop`, `tablespoon`, `teaspoon`
- palm-sized hints

Behavior:

- Returns a frozen Pydantic model.
- Enforces `grams_min <= grams_max` and non-negative bounds.
- Uses a conservative fallback range when the hint is missing, invalid, or unrecognized.
- Runs locally only; it does not call an LLM or any network service.

## Meal Analysis

`services.meal` builds on this catalog and parser to map `FoodComponent` objects into component estimates and meal-level macro intervals. See [docs/meal.md](meal.md).

## Persistence

`services.storage` persists meal estimates and daily totals in a local SQLite ledger. See [docs/storage.md](storage.md).

## Verification

- `pytest tests/nutrition/test_portion_parser.py`
- `pytest tests/nutrition/test_food_data.py`
- `ruff check services/nutrition/`
