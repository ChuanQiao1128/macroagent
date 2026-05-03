# Agent Brief: TASK-006 Food Name Matcher

## Goal

Add deterministic food-name matching over the local USDA and personal nutrition
catalogs.

## User Value

Vision returns short component names such as "rice" or "protein shake". Track A
needs a local matcher that can map those names to `MacroEntry` candidates before
macro ranges can be computed.

## Allowed Files

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

- Add a public matcher API that returns ranked candidates for a query.
- Include a Pydantic result model with at least:
  - `entry`
  - `score`
  - `matched_on`
  - `match_type`
- Support exact name, exact alias, token containment, and lightweight fuzzy matching.
- Prefer personal catalog entries over USDA entries when scores are otherwise tied.
- Keep existing `get_macro_entry()` behavior unchanged and USDA-only.
- Do not require network access or external packages beyond the current project dependencies.
- Add focused tests covering:
  - exact USDA match
  - exact personal alias match
  - personal tie-break preference
  - fuzzy typo match
  - no-match threshold behavior

## Commands

- pytest tests/nutrition/test_food_data.py
- ruff check services/nutrition/

## Budget

- max_cost_usd: 1.50
- max_attempts: 3

## Escalate If

- Need to change the `MacroEntry` schema.
- Need a database or vector store for this task.
- Need external network calls for nutrition data.
