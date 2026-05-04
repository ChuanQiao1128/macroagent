# SQLite Ledger

`services.storage` provides the local-only SQLite persistence layer for meal estimates and daily ledger totals.

## Public API

- `initialize_sqlite_ledger(database_path)`
- `insert_meal_estimate(database_path, meal_estimate, local_date=None, meal_id=None, created_at=None)`
- `fetch_meal_by_id(database_path, meal_id)`
- `fetch_daily_totals(database_path, local_date)`
- `export_ledger_backup(database_path)`
- `StoredMealEstimate`
- `DailyLedgerTotals`

## Backup Export

`export_ledger_backup(database_path)` returns a deterministic, JSON-safe dictionary that can be serialized directly for local backup or inspection.

Top-level fields:

- `format`: `macroagent.sqlite_ledger_backup`
- `export_schema_version`: the backup schema version
- `ledger_schema_version`: the SQLite ledger schema version currently exported
- `schema_migrations`: applied migration versions and timestamps
- `meal_count`: number of exported meals
- `meals`: meal records sorted by `local_date`, `created_at`, then `meal_id`

Each exported meal includes:

- meal identifiers and timestamps
- component counts
- nutrition ranges for `kcal`, `protein_g`, `carbs_g`, `fat_g`, `sugar_g`, `sodium_mg`, and `fiber_g`
- nutrition best estimates for the same seven metrics
- source traces
- the serialized meal estimate payload
- the serialized meal trace versions under `trace_versions`
- component rows sorted by `component_index`

Each exported component includes:

- component metadata and status
- top candidate data
- the selected macro entry when matched
- portion range details
- nutrition ranges and best estimates when available
- source trace data when available
- the serialized component estimate payload

## Behavior

- Uses only the Python standard library `sqlite3` module.
- Initializes a replayable schema and records applied versions in `schema_migrations`.
- Creates one row per meal in `meals`.
- Creates one row per meal component in `meal_component_estimates`.
- Stores local date strings as `YYYY-MM-DD`.
- Stores timestamps as ISO-formatted strings.
- Persists the seven core nutrition ranges, best estimates, component traces, source trace JSON, and serialized meal estimate JSON.
- Round-trips `MealEstimate.trace_versions` through the stored `meal_estimate_json` payload.
- Keeps the ledger local-first and does not require any cloud or network service.
- Treats repeated inserts with the same `meal_id` and identical payload as idempotent.
- Raises `ValueError` when a duplicate `meal_id` is reused with a different payload.
- Returns `None` from `fetch_meal_by_id()` when a meal id is not present.
- Returns zero ranges and arithmetic-midpoint best estimates for empty-day totals.
- Exposes export-only backup behavior for now; there is no public restore/import API yet.
- For the shared trace version constants used by vision, meal, CLI, and export payloads, see [docs/trace.md](trace.md).

## Verification

- `pytest tests/storage/test_sqlite_ledger.py`
- `pytest tests/`
- `ruff check services/`
