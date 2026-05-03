# Agent Brief: TASK-005 Personal Seed Nutrition Catalog

## Goal

Add a local personal seed nutrition catalog with 20 commonly used foods and make it
loadable alongside the USDA seed catalog.

## User Value

Track A needs personal foods before food mapping can prefer user-specific entries over
generic USDA values. This task adds the first local personal food set without requiring
a database or network access.

## Allowed Files

- services/nutrition/**
- services/nutrition/data/personal_seed.json
- services/nutrition/src/food_data.py
- services/nutrition/__init__.py

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

- Provide exactly 20 personal seed entries in JSON.
- Include common personal foods such as branded milk, protein powder, yogurt, eggs,
  coffee, oats, rice, chicken, tuna, tofu, fruit, nuts, and cooking oil.
- Use the same stable `MacroEntry` shape as the USDA catalog:
  - `id`
  - `name`
  - `aliases`
  - `category`
  - `source`
  - `kcal_per_100g`
  - `protein_g_per_100g`
  - `carbs_g_per_100g`
  - `fat_g_per_100g`
- Every personal seed entry has `source == "PERSONAL"`.
- Extend `MacroEntry` source validation to allow both `"USDA"` and `"PERSONAL"`.
- Expose functions to load personal entries separately and to load all available
  nutrition entries together.
- Preserve existing USDA behavior and public APIs from TASK-004.
- Keep exact lookup behavior unchanged; do not add fuzzy matching or ranking in this task.
- Do not require network access.

## Commands

- pytest tests/nutrition/test_food_data.py
- ruff check services/nutrition/

## Budget

- max_cost_usd: 1.50
- max_attempts: 3

## Escalate If

- Need to change existing `FoodComponent` schema.
- Need to fetch external nutrition data over the network.
- Need to add database migrations or SQLite schema before the JSON catalog is usable.
