# Agent Brief: TASK-019 User Correction Loop

## Goal

Add a local user correction model and apply correction-derived priors to portion
estimation.

## User Value

Every time a user corrects "this rice was 200g" or "this was one full bowl", the
system should improve future estimates for similar foods without relying on a
cloud service.

## Allowed Files

- services/storage/**
- services/nutrition/**
- services/meal/**
- tests/storage/**
- tests/nutrition/**
- tests/meal/**
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

- Add a local correction record model with:
  - timestamp
  - component name
  - selected macro entry id/source
  - original portion estimate
  - corrected grams or serving label
  - optional note
- Persist corrections in SQLite without breaking existing ledger data.
- Add an API to fetch correction-derived priors for a food/component.
- Apply simple deterministic priors to portion p50 when enough corrections exist
  for the same macro entry or normalized component.
- Preserve trace fields that show whether a correction prior was applied.
- Add tests for migration replay, insert correction, fetch priors, applying
  priors after threshold, and no-prior behavior before threshold.

## Commands

- pytest tests/storage/ tests/nutrition/ tests/meal/
- pytest tests/
- ruff check services/storage/ services/nutrition/ services/meal/

## Budget

- max_cost_usd: 2.00
- max_attempts: 3

## Escalate If

- Need cloud sync.
- Need user accounts or auth.
- Need a machine-learning model.
