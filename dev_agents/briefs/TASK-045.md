# TASK-045 - AVFoundation Capture and Image Hash

## Goal

Implement the iOS capture service for taking a photo and producing backend image
identity metadata.

## Product value

The smoke test must use a real iPhone camera photo, not a static mock payload.
This task proves photo capture, dimensions, byte size, format, and SHA-256 identity.

## Scope

Implementation may modify:

- `apps/ios/**`

Tester may add:

- `tests/ios/**`

Doc role may update:

- `docs/**`

## Requirements

- Add an `AVFoundation` capture service.
- Request camera permission.
- Capture encoded image bytes.
- Compute SHA-256 hash using CryptoKit.
- Extract width, height, byte size, and format.
- Build the v0.4 `image_identity` payload.
- Keep raw image bytes in memory only for upload; do not persist image files in the
  repo or trace examples.
- Add a manual fallback sample mode for simulator/no-camera environments.

## Acceptance criteria

- Static tests verify AVFoundation and CryptoKit usage.
- Capture metadata builder produces fields matching v0.4 contract names.
- README/runbook explains real-device requirement and camera permission.
- No committed real photo files.

## Commands

- `pytest tests/ios/`
- `ruff check tests/ios`

## Forbidden

- Do not implement CoreMotion or Vision OCR/barcode in this task.
- Do not store raw images in trace artifacts.
- Do not edit `.codex/**`, `.github/**`, `dev_agents/policies/**`,
  `evals/golden_set/**`, `prompts/**`, or `DESIGN_zh*.md`.
