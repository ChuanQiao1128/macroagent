# Agent Brief: TASK-010 Meal Component Mapping Pipeline

## Goal

Connect vision `FoodComponent` objects to nutrition matches, portion ranges, and
macro intervals in a deterministic local pipeline.

## User Value

Track A needs a single local function that can take vision output and return a
traceable meal estimate before UI and persistence work start.

## Allowed Files

- services/meal/**
- services/accounting/**
- services/nutrition/**
- services/vision/**
- docs/**

## Forbidden Files

- prompts/**
- DESIGN_zh.md
- evals/golden_set/**
- .codex/**
- .github/**
- dev_agents/policies/**
- docs/adr/**

## Acceptance

- Add a public meal analysis API that accepts a list of `FoodComponent` objects.
- For each component:
  - run local food matching
  - keep top candidates
  - parse portion hints into gram ranges
  - compute macro intervals for the selected candidate
- Return immutable Pydantic models for component estimates and meal estimates.
- Include trace fields for component name, selected macro entry id/source,
  match score, portion range, and macro interval.
- Components with no confident match should be retained with a clear
  `unmatched` status and should not break the meal estimate.
- Do not call Claude, OpenAI, or network APIs in this task.
- Add tests for matched components, unmatched components, personal preference,
  aggregate macro totals, and trace fields.

## Commands

- pytest tests/
- ruff check services/

## Budget

- max_cost_usd: 2.00
- max_attempts: 3

## Escalate If

- Need to modify prompts.
- Need to call Anthropic/OpenAI during tests.
- Need Streamlit or FastAPI UI changes.
