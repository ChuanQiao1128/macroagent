# TASK-038 - Photo Capture Contract Core

## Goal

Create strict backend schemas for iOS food photo capture metadata and meal photo
analysis contracts.

## Product value

The iPhone app needs a stable contract before any native UI work starts. This task
defines what the phone can send and what the backend may persist.

## Scope

Implement product code under:

- `services/capture/**`

Tester may add tests under:

- `tests/capture/**`

Doc role may update:

- `docs/**`

## Requirements

- Use Pydantic strict models.
- Reject extra fields.
- Do not include raw image bytes, base64 image payloads, local image paths, or raw
  file handles in traceable request/metadata models.
- Model image identity through fields such as image hash, format, dimensions, and
  byte size.
- Include iPhone capture metadata:
  - device model;
  - OS version;
  - camera position;
  - orientation;
  - pitch and roll degrees;
  - focal length or lens hints when available;
  - depth availability and quality;
  - LiDAR availability;
  - barcode payload;
  - OCR text snippets;
  - reference object hint;
  - capture timestamp.
- Define response-facing nutrition metric containers for:
  - `kcal`
  - `protein_g`
  - `carbs_g`
  - `fat_g`
  - `sugar_g`
  - `sodium_mg`
  - `fiber_g`

## Acceptance criteria

- `PhotoAnalyzeRequest` validates realistic iPhone metadata.
- Attempts to include raw image content fields are rejected.
- `PhotoAnalyzeResponse` supports `ACCEPT`, `WARN`, `CLARIFY`, and `BLOCK`.
- Tests cover valid payload, invalid extra fields, raw-image rejection, and seven
  nutrition metrics.
- Existing full test suite remains green.

## Commands

- `pytest tests/capture/`
- `ruff check services/capture tests/capture`

## Forbidden

- Do not add live model calls.
- Do not store raw images in trace artifacts.
- Do not let LLM output calories or macros.
- Do not edit `.codex/**`, `.github/**`, `dev_agents/policies/**`,
  `evals/golden_set/**`, `prompts/**`, or `DESIGN_zh*.md`.
