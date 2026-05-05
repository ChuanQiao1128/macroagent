# TASK-039 - Capture Quality and Scale Evidence Adapter

## Goal

Convert iPhone capture metadata into deterministic scale evidence used by the meal
takeoff pipeline.

## Product value

Portion estimation quality depends on capture-stage evidence. This task turns
iPhone signals into structured `ScaleEvidenceCandidate` and
`ScaleEvidenceResolution` objects.

## Scope

Implement product code under:

- `services/capture/**`
- `services/meal/**` only if a tiny integration helper is needed

Tester may add tests under:

- `tests/capture/**`
- `tests/meal/**` only for integration coverage

Doc role may update:

- `docs/**`

## Requirements

- Consume the schemas from TASK-038.
- Map capture metadata to existing takeoff schema types:
  - `ScaleEvidenceCandidate`
  - `ScaleEvidenceResolution`
  - `MealScaleEvidence`
- Handle these cases deterministically:
  - LiDAR/depth available and usable;
  - barcode or nutrition-label serving available;
  - standard utensil or reference object hint;
  - weak side-angle or no reference object;
  - card-like object with PII risk.
- Reject PII-like card references as unusable for scale.
- Emit trace events through existing trace emitter utilities.
- Keep all decisions source-backed and deterministic.

## Acceptance criteria

- Depth/LiDAR metadata produces stronger scale confidence than photo-only metadata.
- Barcode/label serving metadata maps to barcode or label scale evidence.
- Utensil/reference hints produce weak or medium scale evidence.
- PII-like card hint is rejected and does not become usable scale evidence.
- Missing scale produces `prompt_user_for_reference=True` when the policy requires
  clarification.
- Tests cover every case above.

## Commands

- `pytest tests/capture/`
- `pytest tests/meal/takeoff/test_trace_emitter.py`
- `ruff check services/capture tests/capture`

## Forbidden

- Do not call a model.
- Do not write image bytes, crops, or local file paths into trace events.
- Do not edit `.codex/**`, `.github/**`, `dev_agents/policies/**`,
  `evals/golden_set/**`, `prompts/**`, or `DESIGN_zh*.md`.
