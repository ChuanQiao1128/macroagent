# Agent Brief: TASK-024 Web Upload And Result UI

## Goal

Create the first browser UI for uploading a meal photo, tracking the analysis
job, and reading the seven-metric nutrition result.

## User Value

The product becomes testable without terminal commands. This is the fastest way
to validate the meal-result UX before iOS native development.

## Allowed Files

- apps/web/**
- services/api/**
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

- Scaffold `apps/web` with React, TypeScript, and Tailwind or the repo's
  established frontend stack if one exists by then.
- First screen is the usable app, not a marketing landing page.
- Support image upload, preview, job polling, loading state, failure state, and
  result state.
- Show:
  - kcal
  - protein
  - carbs
  - fat
  - sugar
  - sodium
  - fiber
  - estimate status
  - component matches
  - portion ranges
  - recommended user question
- Include fixture/demo mode so the UI can replay sushi and coffee without a
  real Claude call.
- Add focused tests for result rendering and failed job rendering.
- Update docs with dev server commands.

## Commands

- pytest tests/
- ruff check services tests
- npm test --if-present
- npm run lint --if-present

## Budget

- max_cost_usd: 2.50
- max_attempts: 3

## Escalate If

- Need production auth.
- Need mobile-native work.
- Need to change protected prompts or golden sets.
