# Agent Brief: TASK-015 Component Normalizer

## Goal

Add a deterministic component normalization layer between vision output and
nutrition matching.

## User Value

Vision may return duplicate components, raw visible labels, or multiple
candidates for the same food. A normalizer gives the downstream matcher a clean
and traceable component set without asking an LLM to make final nutrition
decisions.

## Allowed Files

- services/meal/**
- services/vision/**
- tests/meal/**
- docs/**

## Forbidden Files

- services/nutrition/data/**
- services/accounting/**
- services/storage/**
- prompts/**
- DESIGN_zh.md
- evals/golden_set/**
- .codex/**
- .github/**
- dev_agents/policies/**
- docs/adr/**

## Acceptance

- Add public models/functions for normalized meal components.
- Accept both legacy `FoodComponent` and the structured vision response from
  TASK-014.
- Preserve top-k food candidates and visual evidence when available.
- Normalize whitespace/case and merge obvious duplicate components while keeping
  trace references to original component ids/names.
- Carry forward state hints such as cooked/raw/fried/grilled/plain/sauced.
- Carry forward hidden ingredient risks and uncertainty flags.
- Do not perform nutrition matching or macro calculation in this layer.
- Add tests for:
  - legacy input normalization
  - structured input normalization
  - duplicate merge behavior
  - preservation of top-k candidates
  - preservation of hidden ingredient risk flags

## Commands

- pytest tests/meal/
- pytest tests/
- ruff check services/meal/ tests/meal/

## Budget

- max_cost_usd: 1.50
- max_attempts: 3

## Escalate If

- Need to change nutrition data files.
- Need LLM calls.
- Need database writes.
