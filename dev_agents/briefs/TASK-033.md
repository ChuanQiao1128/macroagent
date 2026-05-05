# TASK-033 — ADR Split

## Goal

Split and write stable ADRs so the architecture is readable and not overloaded.

## Files to create / update

```text
docs/adr/ADR-005-ranged-estimate-ledger-policy.md
docs/adr/ADR-006-meal-takeoff-workflow.md
docs/adr/ADR-007-accuracy-stack.md
docs/adr/ADR-008-multi-agent-eligibility-evidence-arbitration.md
```

## ADR-005 content

- Ranged estimate policy
- min/best/max storage
- component_mode_sum caveat
- ledger best estimate vs range metadata
- CLARIFY / log-anyway
- append-only ledger
- version matrix
- portion estimation accuracy reality

## ADR-006 content

- 9-stage Meal Takeoff Workflow
- stage boundaries
- agent vs deterministic components
- intermediate artifacts
- TraceEmitter implementation reference
- PII-safe trace boundary
- Scale Evidence Resolver as Portion Range Refiner substage

## ADR-007 content

- Accuracy Stack: Information Capture, Calibration, Personalization, Active Learning
- release gates
- ablation eval methodology
- cold-start / First 3 Meals Calibration Mode
- weekly uncertainty debt

## ADR-008 content

- Agent eligibility rule
- approved multi-agent positions
- rejected multi-agent patterns
- Evidence Arbitration Layer
- compatibility before conflict
- per-claim arbitration
- conflict resolution order
- cross-cultural component normalization

## Acceptance criteria

- ADRs do not duplicate responsibilities.
- ADR-006 does not become overloaded with accuracy-stack and multi-agent details.
- ADR-008 explicitly rejects LLM voting on calories/macros.
- ADR-007 contains measurable gates.
- Docs are coherent with implemented schemas.

---
