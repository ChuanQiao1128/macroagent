# TASK-054 - Image Privacy, Cache, and Retention Policy

## Goal

Define and implement the local privacy boundary for real image handling, provider
cache keys, and temporary retention.

## Product value

Real users will upload private meal photos. The system must avoid accidental raw
image persistence while still supporting retries, cache hits, and debugging.

## Scope

Implementation may modify:

- `services/api/**`
- `services/capture/**`
- `services/storage/**`
- `services/vision/**`
- `services/meal/**`

Tester may add:

- `tests/api/**`
- `tests/capture/**`
- `tests/storage/**`
- `tests/vision/**`
- `tests/meal/**`

Doc role may update:

- `docs/**`

## Requirements

- Store raw uploaded images only in an explicit temporary intake area.
- Clean temporary image files after successful processing or failed terminal
  states according to a documented retention window.
- Cache structured provider outputs by:
  - normalized image hash;
  - provider name;
  - model/version;
  - prompt hash;
  - schema version.
- Cache only sanitized structured output and provider diagnostics, not raw image
  bytes or local file paths.
- Add privacy boundary tests for traces, ledger rows, cache entries, and API
  responses.
- Update docs with the local retention and deletion contract.

## Acceptance criteria

- Tests prove no trace or ledger payload includes raw bytes, base64 payloads, or
  local image paths.
- Tests prove cache hits avoid repeat provider calls for the same normalized
  image and version tuple.
- Tests prove cache misses occur when provider/model/prompt/schema changes.
- Docs describe what is stored, what is temporary, and what is never persisted.
- Existing full test suite remains green.

## Commands

- `pytest -p no:cacheprovider tests/api tests/capture tests/storage tests/vision tests/meal`
- `ruff check services/api services/capture services/storage services/vision services/meal tests/api tests/capture tests/storage tests/vision tests/meal`

## Forbidden

- Do not commit sample private images.
- Do not add S3, GCS, or production object storage.
- Do not weaken `docs/privacy_trace_boundary.md`.
- Do not edit `.codex/**`, `.github/**`, `dev_agents/policies/**`,
  `evals/golden_set/**`, `prompts/**`, or `DESIGN_zh*.md`.
