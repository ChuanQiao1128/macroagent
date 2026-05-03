# Agent Brief: TASK-003 Vision Result Cache

## Goal

Add deterministic image hashing and result caching for Claude vision meal-photo analysis.

## User Value

Repeated uploads of the same meal photo should not trigger another expensive vision call.

## Allowed Files

- services/vision/src/claude_vision.py
- services/vision/src/cache.py
- services/vision/__init__.py

## Forbidden Files

- prompts/**
- DESIGN_zh.md
- evals/golden_set/**
- .codex/**
- .github/**
- dev_agents/policies/**

## Acceptance

- Compute a stable SHA-256 image hash from the normalized JPEG bytes.
- Allow `ClaudeVisionClient` to use an optional cache object.
- Cache key includes image hash, model name, and prompt text.
- Cache hit returns `FoodComponent[]` without calling Anthropic.
- Cache miss calls Anthropic once and writes the validated result.
- Provide a simple JSON-file cache implementation suitable for local Track A.
- Keep cache writes atomic enough for local single-user use.
- Do not store raw images in the cache.

## Commands

- pytest tests/vision/test_claude_vision.py
- ruff check services/vision/

## Budget

- max_cost_usd: 1.50
- max_attempts: 3

## Escalate If

- Need to change the public `FoodComponent` schema.
- Need to store original image bytes or any user-identifying data.
