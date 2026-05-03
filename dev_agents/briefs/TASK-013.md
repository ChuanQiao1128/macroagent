# Agent Brief: TASK-013 Local CLI Meal Demo

## Goal

Add a small local CLI demo that analyzes a meal image and stores the resulting
meal estimate in the local ledger.

## User Value

Before building UI, Track A needs one command that exercises the local pipeline:
photo input, vision wrapper, food mapping, macro range calculation, and local
persistence.

## Allowed Files

- services/cli/**
- services/meal/**
- services/storage/**
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

- Add a Python CLI entry module that can be run with `python -m ...`.
- Accept:
  - image path
  - SQLite db path
  - optional cache path
  - optional dry-run flag that skips persistence
- Use the existing Claude vision wrapper for real image analysis.
- Keep tests offline by injecting or faking the vision result path.
- Print JSON to stdout with meal id, component estimates, macro ranges, and best
  estimates.
- Persist to SQLite unless dry-run is enabled.
- Add tests for argument parsing, dry-run output, persistence path, and error
  handling without calling network APIs.

## Commands

- pytest tests/
- ruff check services/

## Budget

- max_cost_usd: 2.00
- max_attempts: 3

## Escalate If

- Need a web UI framework.
- Need real API calls during tests.
- Need to modify prompt or golden-set files.
