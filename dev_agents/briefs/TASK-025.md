# Agent Brief: TASK-025 Web Correction Loop

## Goal

Add the first user correction flow for high-impact uncertainty and portion
adjustments in the web app.

## User Value

Photo estimates are often uncertain. Users need a fast way to correct the few
things that materially change the result, such as sauce, sugar, grams, and
piece count.

## Allowed Files

- apps/web/**
- services/api/**
- services/storage/**
- services/meal/**
- tests/**
- docs/**

## Forbidden Files

- services/vision/**
- services/nutrition/data/**
- prompts/**
- DESIGN_zh.md
- evals/golden_set/**
- .codex/**
- .github/**
- dev_agents/policies/**
- docs/adr/**

## Acceptance

- The API accepts corrections for:
  - portion grams
  - piece count
  - sugar packet used/not used
  - sauce/mayo present and amount class
- The web result screen surfaces the recommended correction question first.
- Corrections trigger deterministic recalculation; no new LLM call is required.
- Store original estimate, correction payload, and recalculated estimate.
- Show before/after best estimates for the seven core metrics.
- Tests cover correction persistence and recalculation.

## Commands

- pytest tests/
- ruff check services tests
- npm test --if-present
- npm run lint --if-present

## Budget

- max_cost_usd: 2.50
- max_attempts: 3

## Escalate If

- Need multi-user auth.
- Need HealthKit or iOS changes.
- Need protected prompt changes.
