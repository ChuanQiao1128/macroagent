# MacroAgent v0.4 Serious Food Photo Capture Plan

## Decision

Serious food photo estimation should default to one photo. The next stage is a
backend API contract plus an iOS-native capture vertical slice that returns an
estimate and quick correction hooks without requiring multi-angle capture.

The v0.4 automation starts with mock-first backend and contract work. It does not
add live model calls, does not ask an LLM for calories or macros, and does not store
raw meal images in trace artifacts.

## Product Slice

Target user flow:

```text
iPhone single-photo capture
-> image hash and capture metadata
-> strict backend request schema
-> scale evidence resolution
-> deterministic meal takeoff
-> nutrition response with ACCEPT/WARN/CLARIFY/BLOCK
-> quick corrections for high-impact uncertainty
-> append-only ledger or log-anyway path
```

## Why iOS Before Full Web

iOS can collect capture-stage signals that materially improve portion estimation:

- camera orientation and image dimensions from `AVFoundation`;
- pitch and roll from `CoreMotion`;
- depth and LiDAR availability from AR capture on supported devices;
- barcode and nutrition-label text from local Vision/OCR;
- guided multi-shot state, such as top-down photo plus side photo;
- explicit reference-object hints from user interaction.

Web is still useful, but mainly for internal QA:

- upload fixture images;
- inspect vision output, source matches, portion ranges, trace events, and ledger
  decisions;
- inspect quick corrections and high-impact uncertainty choices;
- reproduce CLARIFY/BLOCK cases quickly.

## v0.4 Automated Tasks

### TASK-038 - Photo Capture Contract Core

Create strict Pydantic schemas for iOS capture metadata and photo analysis
requests/responses. This is the stable contract between the phone app and backend.

Status: verified in `services/capture/src/schemas.py` and `tests/capture/test_photo_capture_contract.py`.

Expected output:

- no raw image bytes or base64 in traceable request models;
- image identity uses hash plus content metadata;
- capture metadata includes orientation, pitch, roll, depth/LiDAR availability,
  barcode payload, OCR text, and reference-object hints;
- tests prove extra fields are rejected and sensitive image payloads are not stored.

### TASK-039 - Capture Quality and Scale Evidence Adapter

Convert iPhone capture metadata into existing `ScaleEvidenceCandidate` and
`ScaleEvidenceResolution` objects.

Status: verified in `services/capture/src/scale_evidence_adapter.py` and
`tests/capture/test_scale_evidence_adapter.py`.

Expected output:

- depth/LiDAR, barcode/label serving, utensil/reference hints, and photo-only cases
  map into deterministic scale evidence;
- card-like PII hints are rejected;
- missing or weak scale evidence produces CLARIFY-ready state when portion ranges
  are too wide;
- every adapter stage emits trace events.

### TASK-040 - Analyze Photo API Facade

Add a mock-first backend facade for `/v1/meals/analyze-photo` semantics without
starting a live web framework yet.

Status: verified in `services/api/src/analyze_photo_facade.py` and
`tests/api/test_analyze_photo_facade.py`.

Expected output:

- strict request and response schema that accepts the TASK-038 payload shape;
- deterministic mock pipeline using existing scale evidence, portion parsing,
  nutrition lookup, evidence arbitration, ledger gating, and trace emission;
- response includes the seven user-facing metrics: `kcal`, `protein_g`, `carbs_g`,
  `fat_g`, `sugar_g`, `sodium_mg`, and `fiber_g`;
- response status supports `ACCEPT`, `WARN`, `CLARIFY`, and `BLOCK`;
- `CLARIFY` returns follow-up questions and can write a ledger entry when
  `log_anyway=true` and a supported reason is supplied;
- `BLOCK` rejects unsupported raw macro input and does not return nutrition;
- response nutrition values come from deterministic recomputation, not LLM text;
- no live model integration.

### TASK-041 - Capture Trace and Privacy Boundary

Harden trace artifacts for photo capture.

Expected output:

- trace stores image hash, capture metadata summary, and scale evidence IDs;
- trace does not store raw image bytes, base64 images, local image paths, or OCR text
  that may contain PII unless explicitly sanitized;
- tests cover privacy failure cases;
- docs explain what iOS may send and what backend may persist.

### TASK-042 - iOS Handoff Contract Package

Prepare the contract package that the native iOS implementation will use next.

Expected output:

- JSON schema export or schema snapshot for the capture request/response models;
- sample iOS payloads for top-down photo, weak side-angle photo, barcode package,
  and missing-scale CLARIFY case;
- Swift-facing field guide documenting which iPhone APIs populate each field;
- tests verify schema examples validate against backend models.

## Stage After v0.4

After TASK-038 through TASK-042 pass, start the native iOS vertical slice:

```text
SwiftUI Capture Screen
-> AVFoundation photo
-> CoreMotion pitch/roll
-> optional depth/LiDAR metadata
-> local barcode/OCR
-> upload to backend contract
-> result screen with portion correction
```

That should be a separate queue because it will involve Xcode project structure,
Swift code, simulator/device testing, and a different build gate.

## Run Command

Use this command for the automated v0.4 backend capture queue:

```bash
cd /Users/qc/Documents/Claude/Projects/NutritionAI && CODEX_PROVIDER_MODE=chatgpt MAX_REPAIR_ATTEMPTS=3 UNATTENDED_MODE=branch AUTO_PUSH=1 caffeinate -dimsu bash scripts/run_photo_capture_until_done.sh
```

If it stops, inspect the last log in `.codex/runs/`, repair or ask Codex to repair,
then rerun the same command. Completed tasks are skipped through the v0.4 state
file.
