# Agent Brief: TASK-004 USDA Seed Nutrition Catalog

## Goal

Add a local USDA-style seed nutrition catalog that Track A can query by food name.

## User Value

Vision components need to map to nutrition entries before MacroAgent can compute calorie
and macro ranges. This task creates the first local food database for that mapping layer.

## Allowed Files

- services/nutrition/**
- services/nutrition/data/usda_seed.json
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

- Provide at least 50 seed food entries covering rice, noodles, bread, chicken, beef,
  pork, fish, egg, dairy, legumes, fruit, vegetables, nuts, oils, and common sauces.
- Store seed entries in JSON so they are inspectable and usable without a database server.
- Define a Pydantic `MacroEntry` model with stable fields:
  - `id`
  - `name`
  - `aliases`
  - `category`
  - `source`
  - `kcal_per_100g`
  - `protein_g_per_100g`
  - `carbs_g_per_100g`
  - `fat_g_per_100g`
- Every seed entry has `source == "USDA"`.
- Expose functions to load all entries and query by exact name or alias, case-insensitively.
- Return defensive copies or immutable model instances so callers cannot mutate the loaded cache.
- Do not add fuzzy matching in this task; TASK-005 will own fuzzy + alias ranking.
- Do not require network access.

## Commands

- pytest tests/nutrition/test_food_data.py
- ruff check services/nutrition/

## Budget

- max_cost_usd: 1.50
- max_attempts: 3

## Escalate If

- Need to change existing `FoodComponent` schema.
- Need to fetch external USDA data over the network.
- Need to add database migrations or SQLite schema before the JSON catalog is usable.
