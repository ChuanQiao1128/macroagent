# Agent Brief: TASK-012 JSON Backup Export

## Goal

Add a JSON backup/export path for local ledger data.

## User Value

The MVP is local-first. Users should be able to inspect and back up their local
meal records without depending on SQLite tooling.

## Allowed Files

- services/storage/**
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

- Add a public export API that reads the SQLite ledger and returns JSON-safe
  dictionaries.
- Include schema/version metadata in the export.
- Include meals, components, macro ranges, best estimates, and trace fields.
- Add a public import/restore API if it can be done safely without broadening
  the task; otherwise document export-only behavior clearly.
- Make repeated exports deterministic for the same database contents.
- Add tests for empty export, populated export, deterministic ordering, and
  JSON serialization.

## Commands

- pytest tests/
- ruff check services/

## Budget

- max_cost_usd: 1.50
- max_attempts: 3

## Escalate If

- Need cloud backup or sync.
- Need encryption/key management.
- Need to change earlier ledger schemas incompatibly.
