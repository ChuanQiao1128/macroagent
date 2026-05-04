# Agent Brief: TASK-021 Result Explainer Without New Numbers

## Goal

Add a result explanation layer that turns the local trace into user-facing text
without allowing the LLM or formatter to introduce new numeric estimates.

## User Value

Users need a concise explanation of the meal estimate, uncertainty drivers, and
what to correct next. The explanation should be readable, but all numbers must
come from the deterministic pipeline.

## Allowed Files

- services/explainer/**
- services/meal/**
- services/accounting/**
- services/cli/**
- tests/**
- docs/**

## Forbidden Files

- services/vision/**
- services/storage/**
- services/nutrition/data/**
- prompts/**
- DESIGN_zh.md
- evals/golden_set/**
- .codex/**
- .github/**
- dev_agents/policies/**
- docs/adr/**

## Acceptance

- Add a deterministic default explainer that generates concise Chinese and
  English summaries from meal estimate traces.
- The explainer must not calculate or invent new nutrition numbers; it may only
  quote values already present in the trace.
- Include:
  - kcal range and best estimate when estimate is complete
  - known-components-only label when incomplete
  - top uncertainty drivers
  - recommended user correction/question when available
- Add an optional interface seam for future LLM-based wording, but keep tests
  offline and deterministic.
- Add CLI support to include the explanation in JSON output.
- Add tests for complete meal, high-impact incomplete meal, no matched
  components, and "no new numbers" behavior.

## Commands

- pytest tests/
- ruff check services tests

## Budget

- max_cost_usd: 2.00
- max_attempts: 3

## Escalate If

- Need real LLM calls for tests.
- Need UI changes.
- Need to modify protected prompt files.
