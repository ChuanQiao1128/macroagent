# Agent Brief: TASK-001 Claude Vision API Integration

## Goal

Implement vision call wrapper that takes a meal photo and returns
FoodComponent[] with confidence scores.

## User Value

This is the first step of MacroAgent's pipeline. Every meal starts here.

## Allowed Files

- services/vision/src/claude_vision.py
- services/vision/__init__.py

## Forbidden Files

- tests/**
- prompts/**
- DESIGN_zh.md
- evals/golden_set/**

## Acceptance

- Accepts image path or bytes.
- Returns Pydantic model FoodComponent[] with name, confidence, portion_hint.
- Uses Claude Sonnet via Anthropic API, not OpenAI, for vision quality.
- JSON Schema enforced; retry once on parse failure.
- Handles HEIC to JPEG, EXIF rotation, and 1024px long-side resize.

## Commands

- pytest tests/vision/test_claude_vision.py
- ruff check services/vision/

## Budget

- max_cost_usd: 1.50
- max_attempts: 2

## Escalate If

- Need API key not in env.
- Need to change FoodComponent schema.
