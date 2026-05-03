# USDA Seed Nutrition Catalog

`services.nutrition` provides the local seed nutrition catalog used by Track A to map food names to macro entries without requiring a database or network access.

## Data Store

- Seed data lives in `services/nutrition/data/usda_seed.json`.
- The catalog is JSON-backed and inspectable in source control.
- The current seed set includes 50+ entries covering rice, noodles, bread, chicken, beef, pork, fish, egg, dairy, legumes, fruit, vegetables, nuts, oils, and common sauces.

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

All seed entries use `source="USDA"`.

## Lookup API

The module exports these helpers:

- `load_macro_entries()`
- `load_all_macro_entries()`
- `get_macro_entry(name_or_alias)`
- `get_macro_entry_by_name(name_or_alias)`
- `find_macro_entry(name_or_alias)`

Lookup behavior is exact-match only:

- case-insensitive
- whitespace-normalized
- matches against the entry `name` and its `aliases`
- does not do fuzzy matching

The loader returns an immutable tuple of frozen `MacroEntry` instances, so callers cannot mutate the cached catalog.

## Verification

- `pytest tests/nutrition/test_food_data.py`
- `ruff check services/nutrition/`

