# TASK-031 — Trace and Ledger Safety Core

## Goal

Add unified trace emission, PII-safe trace contract, append-only ledger correction chain, and version matrix.

## Files to create / update

```text
services/meal/takeoff/trace.py
services/storage/trace_store.py
services/storage/ledger.py
services/meal/takeoff/schemas.py
docs/privacy_trace_boundary.md
tests/meal/takeoff/test_trace_emitter.py
tests/storage/test_append_only_ledger.py
```

## Requirements

1. Add TraceEvent schema.
2. Add TraceEmitter protocol.
3. Add TraceStore with append/get_trace.
4. Add ledger version matrix:
   - calculator_version
   - uncertainty_policy_version
   - energy_density_policy_version
   - scale_evidence_policy_version
   - contract_yaml_version
   - source_dataset_versions
   - takeoff_pipeline_version
   - semantic_judge_version optional
5. Add append-only ledger semantics:
   - new correction creates new row
   - old row remains
   - `supersedes_id` links chain
   - `active` marks latest row
6. Add `user_accepted_wide_range` and `user_decline_clarify_reason`.
7. Add PII-safe trace doc.
8. Ensure trace stores `image_sha256`, not raw image.

## Acceptance criteria

- All takeoff stage stubs can emit TraceEvent.
- TraceEvent requires `pii_safe=True` by default.
- Raw image fields are not present in trace schema.
- Ledger correction creates new entry and deactivates old active entry without deleting it.
- Version matrix must be present on LedgerEntry.
- Tests pass.

## Out of scope

- Full OpenTelemetry integration
- Production database migration
- Cloud object storage

---
