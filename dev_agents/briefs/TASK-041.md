# TASK-041 - Capture Trace and Privacy Boundary

## Goal

Harden photo-capture trace artifacts so the backend records enough evidence for
debugging without storing raw meal images or sensitive OCR content.

## Product value

Users will trust photo logging only if image handling is explicit. This task makes
the capture trace boundary testable before real iOS uploads begin.

## Scope

Implement product code under:

- `services/capture/**`
- `services/storage/**` only if a small trace-store adapter is needed
- `services/meal/**` only if trace event helpers need extension

Tester may add tests under:

- `tests/capture/**`
- `tests/storage/**`
- `tests/meal/**`

Doc role may update:

- `docs/**`

## Requirements

- Create sanitized capture trace artifacts from photo analyze requests.
- Persist only:
  - image hash;
  - image dimensions/format/byte size;
  - capture quality summary;
  - scale evidence IDs;
  - sanitized barcode/OCR availability flags;
  - model/prompt version placeholders when applicable.
- Do not persist:
  - raw image bytes;
  - base64 image data;
  - local filesystem image paths;
  - raw OCR strings that may contain PII;
  - raw barcode strings unless marked safe.
- Emit trace events through `TraceEmitter` or existing trace utilities.
- Preserve append-only ledger correction behavior.

## Acceptance criteria

- Sanitizer removes or rejects raw image bytes, base64 fields, local paths, and raw
  OCR text.
- Trace event payload contains enough non-sensitive capture metadata to debug scale
  evidence decisions.
- Tests cover safe payload, OCR PII risk, local path rejection, and barcode safety.
- Existing trace privacy documentation is updated by the doc role.

## Commands

- `pytest tests/capture/ tests/storage/ tests/meal/takeoff/test_trace_emitter.py`
- `ruff check services/capture services/storage services/meal tests/capture tests/storage`

## Forbidden

- Do not store raw meal images in trace artifacts.
- Do not edit `.codex/**`, `.github/**`, `dev_agents/policies/**`,
  `evals/golden_set/**`, `prompts/**`, or `DESIGN_zh*.md`.
