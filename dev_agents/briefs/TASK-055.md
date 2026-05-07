# TASK-055 - Real Food Evaluation Fixtures

## Goal

Add a replayable evaluation harness for realistic single-photo foods without
committing private real images.

## Product value

Product decisions need repeatable evidence for sushi, coffee, rice/chicken,
mixed dishes, sauces, drinks, blurry images, and no-scale-reference cases.

## Scope

Implementation may modify:

- `evals/fixtures/**`
- `services/cli/**`
- `services/capture/**`
- `services/meal/**`
- `services/nutrition/**`

Tester may add:

- `tests/evals/**`
- `tests/capture/**`
- `tests/meal/**`
- `tests/nutrition/**`

Doc role may update:

- `docs/**`

## Requirements

- Do not commit private raw meal photos.
- Use fixture metadata, synthetic references, sanitized provider outputs, or
  documented local-only image paths ignored by git.
- Add fixtures for at least:
  - sushi;
  - coffee;
  - rice with protein;
  - mixed dish with hidden sauce or oil;
  - blurry or low-quality photo;
  - no scale reference.
- Add an evaluation CLI or extend an existing CLI to report:
  - status distribution;
  - latency budget;
  - nutrition coverage for seven metrics;
  - correction prompt rate;
  - unmatched or high-impact uncertainty rate.
- Keep fixture replay fast and offline by default.

## Acceptance criteria

- Evaluation fixture replay works without live model calls.
- Tests prove every fixture has sanitized metadata, expected status, and expected
  uncertainty/correction behavior.
- Tests prove no fixture references `evals/golden_set/**` or commits raw private
  image content.
- Docs explain how the user can add local private photos for manual testing
  without committing them.
- Existing full test suite remains green.

## Commands

- `pytest -p no:cacheprovider tests/evals tests/capture tests/meal tests/nutrition`
- `ruff check services/cli services/capture services/meal services/nutrition tests/evals tests/capture tests/meal tests/nutrition`

## Forbidden

- Do not edit `evals/golden_set/**`.
- Do not commit real private photos.
- Do not use live model calls in tests.
- Do not edit `.codex/**`, `.github/**`, `dev_agents/policies/**`,
  `prompts/**`, or `DESIGN_zh*.md`.
