# TASK-051 - Background Analysis Job Queue

## Goal

Move meal photo analysis behind a local background job queue with stable states,
polling, retries, and deterministic result serialization.

## Product value

The phone should receive a response quickly after upload, then poll progress while
slow vision work runs in the background. Users should not wait on a blocked HTTP
request.

## Scope

Implementation may modify:

- `services/api/**`
- `services/capture/**`
- `services/meal/**`
- `services/storage/**`
- `services/vision/**`

Tester may add:

- `tests/api/**`
- `tests/capture/**`
- `tests/meal/**`
- `tests/storage/**`

Doc role may update:

- `docs/**`

## Requirements

- Add or complete a local persistent job model for meal analysis.
- Job states must include:
  - `queued`
  - `running_vision`
  - `matching`
  - `calculating`
  - `needs_correction`
  - `complete`
  - `failed`
- The create endpoint should return quickly with a job ID and status.
- A polling endpoint should return current status, failure category, trace ID,
  and final result when available.
- Add deterministic retry handling for transient provider failures.
- Keep fixture mode available for fast local and CI tests.
- Every job stage transition must emit a TraceEvent.
- Do not store raw meal images in trace artifacts.

## Acceptance criteria

- Tests prove create-and-poll behavior without live model calls.
- Tests prove failure states include a stable category and user-safe message.
- Tests prove completed jobs serialize the same seven nutrition metrics as the
  synchronous facade.
- Tests prove re-running or polling a completed job does not repeat expensive
  provider work unnecessarily.
- Existing full test suite remains green.

## Commands

- `pytest -p no:cacheprovider tests/api tests/capture tests/meal tests/storage`
- `ruff check services/api services/capture services/meal services/storage tests/api tests/capture tests/meal tests/storage`

## Forbidden

- Do not add production auth.
- Do not add cloud queues.
- Do not call LLMs from tests.
- Do not edit `.codex/**`, `.github/**`, `dev_agents/policies/**`,
  `evals/golden_set/**`, `prompts/**`, or `DESIGN_zh*.md`.
