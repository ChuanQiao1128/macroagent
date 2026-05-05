# TASK-042 - iOS Handoff Contract Package

## Goal

Generate the backend contract package that the native iOS capture app will use in
the next stage.

## Product value

Before SwiftUI implementation starts, iOS needs stable request/response schemas,
example payloads, and a field guide mapping iPhone APIs to backend fields.

## Scope

Implement product code under:

- `services/capture/**`
- `services/api/**`
- `apps/**` only for generated schema/example artifacts if needed

Tester may add tests under:

- `tests/capture/**`
- `tests/api/**`

Doc role may update:

- `docs/**`

## Requirements

- Export JSON schema or schema snapshots for:
  - photo analyze request;
  - photo analyze response;
  - capture metadata;
  - capture trace artifact.
- Add sample payloads for:
  - top-down photo with depth;
  - weak side-angle photo without reference object;
  - barcode packaged food;
  - missing-scale CLARIFY case.
- Add a Swift-facing field guide that maps:
  - `AVFoundation` fields;
  - `CoreMotion` pitch/roll;
  - depth/LiDAR availability;
  - local Vision OCR/barcode outputs;
  - user-selected reference object hints.
- Keep examples free of real user photos and PII.

## Acceptance criteria

- Every sample request validates against backend models.
- Every sample response validates against backend models.
- Schema export is deterministic and committed.
- Field guide explains which iPhone API should populate each capture metadata field.
- Tests verify schema/example consistency.

## Commands

- `pytest tests/capture/ tests/api/`
- `ruff check services/capture services/api tests/capture tests/api`

## Forbidden

- Do not create a full iOS app in this task.
- Do not add live model calls.
- Do not store real image data or PII in examples.
- Do not edit `.codex/**`, `.github/**`, `dev_agents/policies/**`,
  `evals/golden_set/**`, `prompts/**`, or `DESIGN_zh*.md`.
