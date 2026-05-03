# Agent Brief: TASK-007 Portion Range Parser

## Goal

Implement deterministic parsing from common portion hints into gram ranges.

## User Value

Claude Vision returns natural-language portion hints. MacroAgent needs a
transparent local parser that converts common hints into conservative gram ranges
before calorie and macro intervals can be computed.

## Allowed Files

- services/nutrition/**
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

- Add a public portion parser API that accepts a component name and optional
  `portion_hint`.
- Return an immutable Pydantic model with:
  - `grams_min`
  - `grams_max`
  - `confidence`
  - `source`
  - `reason`
- Support common hints such as:
  - grams, g, kg
  - cup, half cup, bowl, plate
  - slice, piece, egg, scoop, tablespoon, teaspoon
  - palm-sized / palm sized
- Use conservative fallback ranges when hints are absent or unknown.
- Validate `grams_min <= grams_max` and non-negative values.
- Keep the parser deterministic and local; do not call LLMs or network APIs.
- Add focused tests for numeric units, common household units, missing hints,
  invalid text, and source/reason fields.

## Commands

- pytest tests/
- ruff check services/

## Budget

- max_cost_usd: 1.50
- max_attempts: 3

## Escalate If

- Need a full nutrition database.
- Need image segmentation or computer vision changes.
- Need to modify `FoodComponent` or `MacroEntry` schemas.
