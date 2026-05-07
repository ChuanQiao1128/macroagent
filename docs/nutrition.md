# Seed Nutrition Catalog

`services.nutrition` provides local seed nutrition catalogs used by Track A to map food names to nutrition entries without requiring a database or network access.

## Data Store

- USDA seed data lives in `services/nutrition/data/usda_seed.json`.
- Personal seed data lives in `services/nutrition/data/personal_seed.json`.
- Both catalogs are JSON-backed and inspectable in source control.
- The USDA seed set covers the broad generic catalog used for exact lookup.
- The personal seed set contains 20 commonly used foods, including branded milk, protein powder, yogurt, eggs, coffee, oats, rice, chicken, tuna, tofu, fruit, nuts, and cooking oil.
- Downloaded FoodData Central JSON snapshots can be imported into a local SQLite database at `local_outputs/fdc_local/nutrition.db` for broad offline matching without waiting on the FDC API.

## Entry Model

The preferred public model is `NutritionEntry`, a frozen Pydantic model with stable fields:

- `id`
- `name`
- `aliases`
- `category`
- `source`
- `kcal_per_100g`
- `protein_g_per_100g`
- `carbs_g_per_100g`
- `fat_g_per_100g`
- `sugar_g_per_100g`
- `sodium_mg_per_100g`
- `fiber_g_per_100g`

`MacroEntry` remains as a backward-compatible alias for `NutritionEntry`.
`NutritionEntry.source` accepts either `USDA` or `PERSONAL`.

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
- `load_fdc_macro_entries_for_query(query)`
- `load_fdc_local_entries_for_query(query)`
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
- If the local FDC SQLite database exists and local seed matching misses or is low confidence, the matcher searches that database first and maps results into the same `NutritionEntry` shape with `source="USDA"` and ids like `fdc:171831`.
- If no local FDC database result is available and `FDC_API_KEY` is set, the matcher falls back to the FoodData Central API.
- Confident local matches are not replaced by FDC results; FDC is a fallback/expansion path, not a blanket override.
- FDC extraction supports the seven core output metrics: `kcal`, `protein_g`, `carbs_g`, `fat_g`, `sugar_g`, `sodium_mg`, and `fiber_g`.
- FDC responses are cached in `local_outputs/fdc_search_cache.json` by default. Override with `FDC_CACHE_PATH`; disable lookup with `FDC_LOOKUP_ENABLED=0`.
- Local FDC lookup defaults to `local_outputs/fdc_local/nutrition.db`. Override with `FDC_LOCAL_DB_PATH`; disable only the local SQLite path with `FDC_LOCAL_LOOKUP_ENABLED=0`.
- FDC query cleaning removes package/weight noise such as `stick`, `packet`, and `~4 g` so visible items like sugar packets can resolve to nutrition entries.

## Local FDC Import

The local importer builds a small query database from official USDA/FDC JSON downloads:

```bash
python -m services.nutrition.src.fdc_local \
  --db-path local_outputs/fdc_local/nutrition.db \
  local_outputs/fdc_downloads/extracted/foundation/FoodData_Central_foundation_food_json_2026-04-30.json \
  local_outputs/fdc_downloads/extracted/sr_legacy/FoodData_Central_sr_legacy_food_json_2018-04.json \
  local_outputs/fdc_downloads/extracted/fndds/surveyDownload.json
```

The current local snapshot imports Foundation, SR Legacy, and Survey/FNDDS foods. Branded Foods is intentionally separate because the latest JSON snapshot is several gigabytes after extraction.

Exact lookup behavior remains exact-match only:

- case-insensitive
- whitespace-normalized
- matches against the entry `name` and its `aliases`
- does not do fuzzy matching

`get_macro_entry()`, `get_macro_entry_by_name()`, and `find_macro_entry()` continue to resolve against the USDA catalog only.

The loader returns an immutable tuple of frozen `NutritionEntry` instances, so callers cannot mutate the cached catalog.

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
- Uses food-specific household overrides where generic units are too broad, such as one sushi/maki piece.
- Uses a conservative fallback range when the hint is missing, invalid, or unrecognized.
- Runs locally only; it does not call an LLM or any network service.

## Volume and Container Portions

When capture metadata contains a derived food-volume interval, the backend can
convert volume to grams before macro calculation:

```text
food volume p10/p50/p90
-> deterministic density profile
-> gram p10/p50/p90
-> nutrition database per-100g values
```

Public API:

- `VolumeEstimate`
- `estimate_portion_from_volume(component_name, volume_estimate, category_hint=None)`
- `parse_volume_portion_range(...)` as a compatibility alias
- `resolve_density_profile(component_name, category_hint=None)`
- `resolve_manual_container_volume_estimate(reference_object_hint)`

Manual container behavior:

- Only explicit known-container hints such as `container_rice_bowl_300ml` or
  `container_coffee_mug_240ml` are converted into `manual_container` volume
  estimates.
- Generic reference objects such as forks, plates, and soda cans are not treated
  as food volume.
- The result still carries uncertainty flags, because the final weight depends on
  food density and fill level.

## Meal Analysis

`services.meal` builds on this catalog and parser to map `FoodComponent` objects into component estimates and meal-level macro intervals. See [docs/meal.md](meal.md).

## Trace Metadata

The shared version constants used in meal traces live in [docs/trace.md](trace.md) and are exported from `services.nutrition.src.version_metadata`.

## Persistence

`services.storage` persists meal estimates and daily totals in a local SQLite ledger and exposes a JSON backup export API for inspection and backup. See [docs/storage.md](storage.md).

## Verification

- `pytest tests/nutrition/test_portion_parser.py`
- `pytest tests/nutrition/test_food_data.py`
- `ruff check services/nutrition/`
