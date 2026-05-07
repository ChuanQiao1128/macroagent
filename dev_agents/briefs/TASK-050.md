# TASK-050 - Real Vision Job Provider and Image Intake

## Goal

Connect the one-photo analysis path to a real structured vision provider while
preserving fixture and mock modes for normal tests.

## Product value

Users should be able to take a real meal photo and receive food candidates,
portion evidence, and uncertainty flags instead of the current deterministic
seed-only response.

## Scope

Implementation may modify:

- `services/api/**`
- `services/capture/**`
- `services/vision/**`
- `services/meal/**`
- `services/storage/**`

Tester may add:

- `tests/api/**`
- `tests/capture/**`
- `tests/vision/**`
- `tests/meal/**`

Doc role may update:

- `docs/**`

## Requirements

- Keep all live vision/model outputs behind strict Pydantic schemas.
- Do not let Claude, OpenAI, or any LLM output final calories or macros.
- Add an image intake boundary that accepts a real uploaded image for local
  development but stores only hash, format, dimensions, byte size, and sanitized
  metadata in traceable artifacts.
- Route live image analysis through a provider abstraction that can support:
  - offline fixture mode;
  - Claude CLI subscription mode;
  - future API provider mode.
- Enforce schema validation and retry once on malformed structured vision output.
- Convert structured vision output into the existing deterministic takeoff and
  nutrition calculation path.
- Preserve mock-first behavior for CI and unit tests.
- Emit a TraceEvent for every new takeoff or provider stage.

## Acceptance criteria

- `POST /v1/meals/analyze-photo` or the current facade can analyze a real local
  image when explicitly configured for live vision.
- Offline tests do not require network access, API keys, or Claude subscription.
- Trace artifacts never contain raw image bytes, base64 image payloads, or local
  image paths.
- Tests cover:
  - fixture provider path;
  - malformed provider output retry;
  - raw image exclusion from trace and ledger payloads;
  - live-provider disabled default behavior.
- Existing full test suite remains green.

## Commands

- `pytest -p no:cacheprovider tests/api tests/capture tests/vision tests/meal`
- `ruff check services/api services/capture services/vision services/meal tests/api tests/capture tests/vision tests/meal`

## Forbidden

- Do not add production cloud storage.
- Do not commit real private meal images.
- Do not call Anthropic/OpenAI from the iOS app.
- Do not let LLM output final nutrition numbers.
- Do not edit `.codex/**`, `.github/**`, `dev_agents/policies/**`,
  `evals/golden_set/**`, `prompts/**`, or `DESIGN_zh*.md`.
