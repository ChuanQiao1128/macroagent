# Agent Brief: TASK-009 Best Estimate Selection

## Goal

Add deterministic best-estimate selection for macro intervals.

## User Value

The product displays both a range and a practical single estimate. The single
estimate must be derived from the interval in a deterministic, testable way.

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

- Add a public API that converts macro ranges into best estimates.
- Use geometric midpoint for positive ranges.
- Fall back to arithmetic midpoint when either bound is zero.
- Preserve kcal, protein, carbs, and fat.
- Include the estimation method in the returned model.
- Keep all behavior deterministic and local.
- Add tests for positive ranges, zero-inclusive ranges, equal bounds, invalid
  ranges, and aggregate meal estimates.

## Commands

- pytest tests/
- ruff check services/

## Budget

- max_cost_usd: 1.50
- max_attempts: 3

## Escalate If

- Need to change existing public schemas from prior tasks.
- Need user profile data or goals.
- Need an LLM call.
