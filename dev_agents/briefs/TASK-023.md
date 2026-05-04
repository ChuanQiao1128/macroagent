# Agent Brief: TASK-023 Meal Analysis Job API

## Goal

Add a backend API layer for asynchronous meal analysis jobs so Web and iOS
clients do not block while Claude Vision runs.

## User Value

Users should upload a photo and immediately see a stable job state. Slow Claude
calls should not freeze the frontend or lose the uploaded meal.

## Allowed Files

- services/api/**
- services/cli/**
- services/storage/**
- services/vision/**
- services/meal/**
- services/nutrition/**
- tests/**
- docs/**

## Forbidden Files

- services/nutrition/data/**
- prompts/**
- DESIGN_zh.md
- evals/golden_set/**
- .codex/**
- .github/**
- dev_agents/policies/**
- docs/adr/**

## Acceptance

- Add a FastAPI app with:
  - `POST /meal-analyses` to create an analysis job from an image upload.
  - `GET /meal-analyses/{job_id}` to fetch status and result.
  - fixture mode for offline testing with precomputed vision JSON.
- Job states must include:
  - `queued`
  - `running_vision`
  - `matching`
  - `needs_confirmation`
  - `complete`
  - `failed`
- Persist jobs and final results in SQLite for local development.
- Do not run long analysis inside the request handler in a way that blocks the
  HTTP response.
- Return the same seven-metric result shape currently printed by the CLI.
- Add tests for upload, polling, fixture-mode completion, failure state, and
  result serialization.
- Update docs with local run commands.

## Commands

- pytest tests/
- ruff check services tests

## Budget

- max_cost_usd: 2.00
- max_attempts: 3

## Escalate If

- Need auth/user accounts.
- Need cloud object storage.
- Need changes to protected prompts or golden sets.
