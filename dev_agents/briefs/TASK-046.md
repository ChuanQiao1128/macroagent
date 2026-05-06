# TASK-046 - CoreMotion and Vision Metadata

## Goal

Add iPhone capture metadata from CoreMotion and local Vision barcode/OCR to the
native smoke app.

## Product value

The iPhone can provide scale and quality signals that Web capture cannot. This
task adds the Apple-specific assistance needed for serious food photo estimation.

## Scope

Implementation may modify:

- `apps/ios/**`

Tester may add:

- `tests/ios/**`

Doc role may update:

- `docs/**`

## Requirements

- Capture pitch and roll near shutter time using CoreMotion.
- Add local barcode detection using Vision.
- Add local OCR snippets using Vision.
- Keep OCR snippets short and food/package oriented.
- Add reference object hint selection in the UI.
- Populate v0.4 capture metadata fields:
  - `pitch_degrees`
  - `roll_degrees`
  - `barcode_payload`
  - `barcode_payload_safe`
  - `ocr_text_snippets`
  - `reference_object_hint`
  - `depth_available`
  - `depth_quality`
  - `lidar_available`

## Acceptance criteria

- Static tests verify CoreMotion and Vision usage.
- Metadata builder uses exact backend field names.
- UI exposes server URL and reference object hint controls.
- README documents privacy handling for OCR/barcode values.

## Commands

- `pytest tests/ios/`
- `ruff check tests/ios`

## Forbidden

- Do not send OCR snippets that look like email/phone/long identifiers in examples.
- Do not add live model calls.
- Do not edit `.codex/**`, `.github/**`, `dev_agents/policies/**`,
  `evals/golden_set/**`, `prompts/**`, or `DESIGN_zh*.md`.
