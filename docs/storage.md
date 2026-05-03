# SQLite Ledger

`services.storage` provides the local-only SQLite persistence layer for meal estimates and daily ledger totals.

## Public API

- `initialize_sqlite_ledger(database_path)`
- `insert_meal_estimate(database_path, meal_estimate, local_date=None, meal_id=None, created_at=None)`
- `fetch_meal_by_id(database_path, meal_id)`
- `fetch_daily_totals(database_path, local_date)`
- `StoredMealEstimate`
- `DailyLedgerTotals`

## Behavior

- Uses only the Python standard library `sqlite3` module.
- Initializes a replayable schema and records applied versions in `schema_migrations`.
- Creates one row per meal in `meals`.
- Creates one row per meal component in `meal_component_estimates`.
- Stores local date strings as `YYYY-MM-DD`.
- Stores timestamps as ISO-formatted strings.
- Persists macro ranges, best estimates, component traces, source trace JSON, and serialized meal estimate JSON.
- Keeps the ledger local-first and does not require any cloud or network service.
- Treats repeated inserts with the same `meal_id` and identical payload as idempotent.
- Raises `ValueError` when a duplicate `meal_id` is reused with a different payload.
- Returns `None` from `fetch_meal_by_id()` when a meal id is not present.
- Returns zero ranges and arithmetic-midpoint best estimates for empty-day totals.

## Verification

- `pytest tests/storage/test_sqlite_ledger.py`
- `pytest tests/`
- `ruff check services/`
