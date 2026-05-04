# Agent Brief: TASK-017 Portion Engine Percentile Ranges

## Goal

Upgrade portion estimation from simple min/max gram ranges to percentile-based
portion estimates with p10, p50, and p90.

## User Value

MacroAgent should expose honest uncertainty while still providing a practical
best estimate. Percentiles are better calibrated than a single min/max range and
let future evals measure coverage.

## Allowed Files

- services/nutrition/**
- services/accounting/**
- services/meal/**
- tests/nutrition/**
- tests/accounting/**
- tests/meal/**
- docs/**

## Forbidden Files

- services/vision/**
- services/storage/**
- prompts/**
- DESIGN_zh.md
- evals/golden_set/**
- .codex/**
- .github/**
- dev_agents/policies/**
- docs/adr/**

## Acceptance

- Add a portion estimate model with:
  - `grams_p10`
  - `grams_p50`
  - `grams_p90`
  - `confidence`
  - `source`
  - `reason`
  - uncertainty flags
- Keep backward-compatible min/max access or conversion for existing calculators.
- Parse explicit grams with tighter percentile ranges.
- Parse common visual/household hints with wider percentile ranges.
- For unknown hints, return a conservative low-confidence estimate with flags.
- Update macro calculation to use p10/p50/p90 where available while preserving
  min/max compatibility.
- Add tests for explicit grams, cup/bowl/palm hints, unknown hints, p50 best
  estimate, and invalid percentile ordering.

## Commands

- pytest tests/nutrition/ tests/accounting/ tests/meal/
- pytest tests/
- ruff check services/

## Budget

- max_cost_usd: 2.00
- max_attempts: 3

## Escalate If

- Need image segmentation or scale-reference detection.
- Need user correction history before local defaults work.
- Need to change protected design files.
