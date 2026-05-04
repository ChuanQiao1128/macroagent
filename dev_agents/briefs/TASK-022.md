# Agent Brief: TASK-022 Claude CLI Vision Diagnostics

## Goal

Harden real Claude CLI subscription vision calls so failures are diagnosable and
do not disappear behind a generic schema error.

## User Value

Real photo testing depends on Claude CLI subscription auth. When it fails, the
developer needs the raw failure category and enough metadata to repair quickly
without rerunning expensive calls blindly.

## Allowed Files

- services/vision/**
- services/cli/**
- tests/vision/**
- tests/cli/**
- docs/**

## Forbidden Files

- services/nutrition/data/**
- services/storage/**
- prompts/**
- DESIGN_zh.md
- evals/golden_set/**
- .codex/**
- .github/**
- dev_agents/policies/**
- docs/adr/**

## Acceptance

- Claude CLI prompt input is passed through stdin, not as the final command
  argument after variadic CLI flags.
- Claude CLI is constrained to image reading only; it must not run Bash or edit
  files during vision calls.
- The subprocess removes `ANTHROPIC_API_KEY` so subscription auth remains the
  default path.
- Add explicit error categories for:
  - CLI process failure
  - malformed JSON output
  - missing `structured_output`
  - schema validation failure
  - timeout
- Add optional debug capture for failed raw Claude CLI stdout/stderr under
  `local_outputs/vision_failures/` when `VISION_DEBUG_CAPTURE=1`.
- Tests must mock subprocess calls and remain offline.
- Update docs with the real-call latency and failure behavior.

## Commands

- pytest tests/vision/test_claude_vision.py tests/cli/test_meal_demo.py
- ruff check services/vision tests/vision services/cli tests/cli

## Budget

- max_cost_usd: 1.00
- max_attempts: 3

## Escalate If

- Need to change product prompt files.
- Need real Claude calls in tests.
