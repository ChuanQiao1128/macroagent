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

## Lookup API

The module exports these helpers:

- `load_macro_entries()`
- `load_personal_macro_entries()`
- `load_all_macro_entries()`
- `get_macro_entry(name_or_alias)`
- `get_macro_entry_by_name(name_or_alias)`
- `find_macro_entry(name_or_alias)`

Loader behavior:

- `load_macro_entries()` returns the USDA catalog.
- `load_personal_macro_entries()` returns the personal seed catalog.
- `load_all_macro_entries()` returns USDA and personal entries together.

Lookup behavior is exact-match only:

- case-insensitive
- whitespace-normalized
- matches against the entry `name` and its `aliases`
- does not do fuzzy matching

`get_macro_entry()`, `get_macro_entry_by_name()`, and `find_macro_entry()` continue to resolve against the USDA catalog only.

The loader returns an immutable tuple of frozen `MacroEntry` instances, so callers cannot mutate the cached catalog.

## Verification

- `pytest tests/nutrition/test_food_data.py`
- `ruff check services/nutrition/`
