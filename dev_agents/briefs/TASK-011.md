# Agent Brief: TASK-011 SQLite Ledger Schema

## Goal

Add a local SQLite persistence layer for meal estimates and daily ledger totals.

## User Value

Track A needs local-first persistence so uploaded meals and computed estimates
survive process restarts without requiring a cloud database.

## Allowed Files

- services/storage/**
- services/meal/**
- services/accounting/**
- docs/**

## Forbidden Files

- services/vision/**
- prompts/**
- DESIGN_zh.md
- evals/golden_set/**
- .codex/**
- .github/**
- dev_agents/policies/**
- docs/adr/**

## Acceptance

- Use Python stdlib `sqlite3`; do not add external database dependencies.
- Add a replayable schema initializer/migration function.
- Store:
  - meals
  - component estimates
  - macro ranges and best estimates
  - source trace JSON
- Add public APIs to initialize the database, insert a meal estimate, fetch a
  meal by id, and fetch daily totals.
- Use ISO timestamps and local date strings.
- Preserve local-first behavior; no network or cloud services.
- Add tests using temporary SQLite files for migration replay, insert/readback,
  daily totals, and empty-day behavior.

## Commands

- pytest tests/
- ruff check services/

## Budget

- max_cost_usd: 2.00
- max_attempts: 3

## Escalate If

- Need external database services.
- Need to alter protected eval or prompt files.
- Need user authentication.
