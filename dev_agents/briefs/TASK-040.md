# TASK-040 - Analyze Photo API Facade

## Goal

Build a mock-first backend facade for the future `/v1/meals/analyze-photo` API.

## Product value

The iOS app needs one stable call that turns a captured food photo plus metadata
into a user-facing nutrition result. This task creates the API semantics without
adding a live web server or model call yet.

## Scope

Implement product code under:

- `services/api/**`
- `services/capture/**`
- `services/meal/**` only for integration helpers

Tester may add tests under:

- `tests/api/**`
- `tests/capture/**`

Doc role may update:

- `docs/**`

## Requirements

- Accept the strict request models from TASK-038.
- Use deterministic mock component data only.
- Use existing deterministic modules for:
  - scale evidence;
  - portion range;
  - source-backed nutrition values;
  - macro/nutrition recomputation;
  - evidence arbitration;
  - ledger gate;
  - trace emission.
- Return strict response models with:
  - status: `ACCEPT`, `WARN`, `CLARIFY`, or `BLOCK`;
  - nutrition intervals for seven metrics;
  - clarify questions when needed;
  - trace ID;
  - ledger entry ID when written;
  - confidence or uncertainty summary.
- Support log-anyway for CLARIFY without weakening append-only ledger rules.

## Acceptance criteria

- ACCEPT fixture returns a complete nutrition response.
- WARN fixture returns a complete response with uncertainty flags.
- CLARIFY fixture returns questions and can log anyway when requested.
- BLOCK fixture refuses unsupported LLM/raw macro input.
- Response nutrition values are computed by deterministic code, not copied from LLM
  text.
- Tests cover all four statuses.

## Commands

- `pytest tests/api/ tests/capture/`
- `ruff check services/api services/capture tests/api tests/capture`

## Forbidden

- Do not add FastAPI or any web framework unless already present.
- Do not add live Anthropic/OpenAI calls.
- Do not let LLM output final calories/macros.
- Do not store raw images in trace artifacts.
- Do not edit `.codex/**`, `.github/**`, `dev_agents/policies/**`,
  `evals/golden_set/**`, `prompts/**`, or `DESIGN_zh*.md`.
