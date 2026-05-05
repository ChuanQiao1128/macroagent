# TASK-037 — Integration Smoke Pipeline

## Goal

Build a deterministic mock pipeline connecting schemas, trace, range calculator, arbitration, and ledger gate.

## Requirements

Use mock inputs only.

Pipeline:

```text
MealCase mock input
→ mock ComponentTakeoff output
→ mock SourceSeed candidates
→ mock SourceCritic result
→ mock ScaleEvidenceResolution
→ PortionRange
→ MacroQuantity
→ EvidenceArbitration
→ LedgerGate
→ TraceStore
→ LedgerEntry
```

## Acceptance criteria

- One ACCEPT fixture runs end-to-end.
- One WARN fixture runs end-to-end.
- One CLARIFY fixture runs end-to-end and supports log-anyway.
- One BLOCK fixture blocks unsupported LLM macro.
- All stages emit trace events.
- Ledger entry includes version matrix.
