# TASK-035 — Minimal UX Components

## Goal

Implement minimal user-facing components for ranged estimate and trace entry.

## Files to create / update

```text
frontend/components/EstimateRangeCard.tsx
frontend/components/ClarificationPrompt.tsx
frontend/components/LogAnywayButton.tsx
frontend/components/TakeoffTracePanel.tsx
frontend/components/WeeklyReviewCard.tsx
frontend/components/UncertaintyDebtCard.tsx
frontend/pages/meal/[id].tsx or equivalent
```

## Requirements

1. EstimateRangeCard shows:
   - best estimate
   - likely range
   - confidence label
   - main uncertainty driver
2. ClarificationPrompt shows at most one question.
3. LogAnywayButton records wide-range flag.
4. TakeoffTracePanel is secondary, collapsed by default.
5. WeeklyReviewCard shows uncertainty debt.

## Acceptance criteria

- User can log a meal without opening Trace.
- User can select log anyway from CLARIFY state.
- Trace is discoverable but not required.
- UI copy avoids medical claims.

---
