# Agent Brief: TASK-016 State-Aware Nutrition Matcher

## Goal

Upgrade nutrition matching to use top-k vision candidates and food state hints,
and make personal-catalog priority conditional rather than unconditional.

## User Value

Personal entries are useful, but they should not beat a better USDA/FDC-style
match when the preparation state differs. This task reduces wrong matches such
as grilled chicken breast being mapped to a personal sauced chicken item.

## Allowed Files

- services/nutrition/**
- services/meal/**
- tests/nutrition/**
- tests/meal/**
- docs/**

## Forbidden Files

- services/vision/**
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

- Extend matcher result trace with a human-readable reason string.
- Support matching over multiple vision candidates instead of only the first
  visible name.
- Incorporate preparation/state hints where present:
  - cooked/raw
  - fried/grilled/boiled/plain/sauced
- Personal entries may receive a priority bonus only when:
  - match score is high enough
  - state/preparation does not conflict
  - the entry is not marked low confidence or stale
- Preserve existing simple `match_food_name()` behavior for callers that pass a
  plain query string.
- Return top-k candidates with source, score, match type, matched_on, and reason.
- Add tests for:
  - personal exact frequent match wins
  - personal state conflict loses to USDA
  - top-k vision candidate fallback
  - reason strings
  - no regression to old exact/fuzzy behavior

## Commands

- pytest tests/nutrition/ tests/meal/
- pytest tests/
- ruff check services/nutrition/ services/meal/

## Budget

- max_cost_usd: 2.00
- max_attempts: 3

## Escalate If

- Need external USDA API calls.
- Need new nutrition source fields that would break existing data files.
- Need to modify vision prompts.
