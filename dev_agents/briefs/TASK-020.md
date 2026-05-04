# Agent Brief: TASK-020 Trace Version Metadata

## Goal

Persist and expose model, prompt, nutrition source, matcher, portion engine, and
calculator versions in every meal trace.

## User Value

When estimates change over time, MacroAgent needs to explain why. Versioned trace
metadata makes debugging, eval comparisons, and user trust possible.

## Allowed Files

- services/vision/**
- services/nutrition/**
- services/accounting/**
- services/meal/**
- services/storage/**
- services/cli/**
- tests/**
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

- Add stable version constants for:
  - vision schema
  - model name
  - prompt text/version or prompt hash
  - nutrition catalog version
  - matcher version
  - portion engine version
  - macro calculator version
  - ledger schema version
- Include version metadata in meal estimates and CLI JSON output.
- Persist version metadata in SQLite trace JSON.
- Export version metadata in JSON backups.
- Add tests proving version metadata appears in:
  - vision output trace
  - meal estimate
  - CLI output
  - SQLite readback/export
- Do not add new external dependencies.

## Commands

- pytest tests/
- ruff check services tests

## Budget

- max_cost_usd: 2.00
- max_attempts: 3

## Escalate If

- Need to edit protected prompt files.
- Need cloud observability integration.
- Need to rewrite existing storage rows manually.
