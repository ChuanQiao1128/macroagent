# Local CLI Meal Demo

`services.cli` provides a small local demo for the end-to-end meal pipeline.

## Entry Points

- `python -m services.cli`
- `python -m services.cli.meal_demo`

## Usage

```bash
python -m services.cli.meal_demo IMAGE_PATH DB_PATH [--cache-path CACHE_JSON] [--dry-run]
```

Required arguments:

- `image_path`: path to the meal image to analyze
- `db_path`: path to the local SQLite ledger

Optional flags:

- `--cache-path`: JSON cache file for vision responses
- `--dry-run`: skip SQLite persistence and only print the computed estimate

## Behavior

- Uses the Claude vision wrapper to analyze the image when no injected vision result is provided.
- Passes the resulting `FoodComponent` objects through `services.meal`.
- Computes meal-level macro ranges and best estimates with `services.accounting`.
- Persists the meal to SQLite through `services.storage` unless `--dry-run` is set.
- Prints a JSON object to stdout with the meal id, component estimates, macro ranges, and best estimates.

## Offline Testing

The implementation includes a test-only seam for precomputed vision payloads so CLI tests can run without network access.
Those tests exercise argument parsing, dry-run output, persistence, and error handling without calling Claude.

## Verification

- `pytest tests/cli/test_meal_demo.py`
- `pytest tests/`
- `ruff check services/`
