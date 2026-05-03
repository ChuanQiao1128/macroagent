# Agent Brief: TASK-008 Macro Interval Calculator

## Goal

Implement deterministic macro range calculation from a `MacroEntry` and a gram
range.

## User Value

MacroAgent's core product promise is honest uncertainty. Given a mapped food and
portion range, it must compute kcal/protein/carbs/fat intervals without asking an
LLM to do arithmetic.

## Allowed Files

- services/accounting/**
- services/nutrition/**
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

- Add a deterministic public API for calculating macro intervals.
- Accept a `MacroEntry` and a portion gram range.
- Return immutable Pydantic models for:
  - per-food macro interval
  - aggregate meal macro interval
- Include kcal, protein, carbs, and fat ranges.
- Use per-100g macro values from `MacroEntry` only.
- Validate non-negative gram ranges and `grams_min <= grams_max`.
- Round outputs consistently to one decimal place.
- Add tests for single food, aggregate meal, zero grams, invalid ranges, and
  source trace fields.

## Commands

- pytest tests/
- ruff check services/

## Budget

- max_cost_usd: 1.50
- max_attempts: 3

## Escalate If

- Need to change `MacroEntry`.
- Need LLM calls for arithmetic.
- Need a database before pure calculation works.
