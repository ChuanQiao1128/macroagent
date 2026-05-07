# TASK-056 - Dish Template and RAG Seed Layer

## Goal

Productize a deterministic dish-template seed layer for common mixed meals and
retrieval candidates.

## Product value

Single photos often hide ingredients and portion details. Dish templates help the
system reason about likely components, hidden oil/sauce, and serving priors while
keeping final nutrition calculation source-backed.

## Scope

Implementation may modify:

- `services/meal/**`
- `services/nutrition/**`
- `services/storage/**`
- `services/capture/**`

Tester may add:

- `tests/meal/**`
- `tests/nutrition/**`
- `tests/storage/**`
- `tests/capture/**`

Doc role may update:

- `docs/**`

## Requirements

- Add a strict dish template model for common meals such as:
  - sushi;
  - fried rice;
  - ramen or noodle soup;
  - salad with dressing;
  - coffee with add-ins;
  - rice bowl;
  - sandwich or burger.
- Templates may provide candidate components, hidden-ingredient risks, serving
  priors, and clarification triggers.
- Templates must not provide final calories or final macros.
- Retrieval must be deterministic and testable; vector/RAG work may be stubbed
  behind an interface if needed.
- Tie templates into the takeoff path as evidence, not as a replacement for FDC
  or personal catalog nutrition sources.
- Emit TraceEvents for template retrieval and template evidence application.

## Acceptance criteria

- Tests prove dish templates can be retrieved from food candidates and OCR/menu
  hints when available.
- Tests prove hidden oil/sauce or drink add-in priors can trigger correction
  prompts.
- Tests prove final seven metrics still come from deterministic recomputation.
- Docs explain how this seed layer differs from LLM calorie guessing.
- Existing full test suite remains green.

## Commands

- `pytest -p no:cacheprovider tests/meal tests/nutrition tests/storage tests/capture`
- `ruff check services/meal services/nutrition services/storage services/capture tests/meal tests/nutrition tests/storage tests/capture`

## Forbidden

- Do not introduce live vector database services.
- Do not let templates become final macro sources.
- Do not let LLM output final nutrition numbers.
- Do not edit `.codex/**`, `.github/**`, `dev_agents/policies/**`,
  `evals/golden_set/**`, `prompts/**`, or `DESIGN_zh*.md`.
