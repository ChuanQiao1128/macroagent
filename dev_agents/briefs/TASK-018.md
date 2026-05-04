# Agent Brief: TASK-018 High-Impact Uncertainty Gate

## Goal

Add an uncertainty gate that distinguishes low-impact unmatched components from
high-impact uncertainty that should block or qualify the final estimate.

## User Value

Silently excluding sauce, oil, dessert, or other high-impact unmatched components
can severely undercount a meal. The system should mark incomplete estimates and
recommend a targeted user question when the uncertainty materially affects kcal
or fat.

## Allowed Files

- services/meal/**
- services/accounting/**
- services/nutrition/**
- tests/meal/**
- tests/accounting/**
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

- Add meal-level estimate status:
  - `complete`
  - `incomplete_low_impact`
  - `incomplete_high_impact`
- Add high-impact detection for unmatched or hidden-risk components such as:
  - creamy/oily sauce
  - oil/butter
  - nuts/nut butter
  - cheese/cream
  - sugary drinks/dessert
- Preserve component traces and unmatched reasons.
- For high-impact unmatched components, do not present the known-component
  best estimate as if it were complete.
- Add a recommended user question when one uncertainty dominates.
- Add tests for:
  - low-impact unmatched vegetable
  - high-impact unmatched sauce
  - hidden oil/butter risk
  - known-components-only macro range labeling
  - recommended question selection

## Commands

- pytest tests/meal/ tests/accounting/
- pytest tests/
- ruff check services/meal/ services/accounting/

## Budget

- max_cost_usd: 2.00
- max_attempts: 3

## Escalate If

- Need LLM calls for question generation.
- Need UI changes.
- Need to alter storage schema before the in-memory model works.
