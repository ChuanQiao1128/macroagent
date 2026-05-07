# TASK-053 - Correction Persistence and Personal Priors

## Goal

Persist quick corrections as append-only events and use them to improve later
estimates for the same user and food class.

## Product value

If a user corrects sushi pieces, rice portion, coffee sugar, or sauce once, the
next similar meal should start closer to their real habit.

## Scope

Implementation may modify:

- `services/api/**`
- `services/capture/**`
- `services/meal/**`
- `services/nutrition/**`
- `services/storage/**`

Tester may add:

- `tests/api/**`
- `tests/capture/**`
- `tests/meal/**`
- `tests/nutrition/**`
- `tests/storage/**`

Doc role may update:

- `docs/**`

## Requirements

- Add an append-only correction event model.
- Store original estimate, correction selection, recomputed estimate, user ID,
  food/component target, and version matrix.
- Never mutate or delete the original ledger estimate when applying a correction.
- Add a deterministic personal prior lookup for common correction types:
  - portion size;
  - consumed fraction;
  - sauce/oil;
  - coffee sugar or milk add-ins.
- Use prior lookup as evidence for future estimates without making it the only
  source of truth.
- Emit TraceEvents for correction ingestion, recomputation, and prior application.

## Acceptance criteria

- Tests prove correction events are append-only.
- Tests prove a correction recomputes seven metrics deterministically.
- Tests prove a later similar request can use the user's prior to adjust the
  default portion or add-in assumption.
- Tests prove cross-user correction leakage cannot happen.
- Existing full test suite remains green.

## Commands

- `pytest -p no:cacheprovider tests/api tests/capture tests/meal tests/nutrition tests/storage`
- `ruff check services/api services/capture services/meal services/nutrition services/storage tests/api tests/capture tests/meal tests/nutrition tests/storage`

## Forbidden

- Do not overwrite ledger rows in place.
- Do not add cloud auth.
- Do not let LLM invent corrected nutrition numbers.
- Do not edit `.codex/**`, `.github/**`, `dev_agents/policies/**`,
  `evals/golden_set/**`, `prompts/**`, or `DESIGN_zh*.md`.
