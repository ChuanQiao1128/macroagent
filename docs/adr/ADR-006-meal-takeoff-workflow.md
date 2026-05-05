# ADR-006: Meal Takeoff Workflow

Date: 2026-05-05
Status: Accepted

## Context

The meal pipeline needs clear stage boundaries so model calls, deterministic
services, policy gates, and ledger writes can evolve independently. Without
explicit boundaries, failures become hard to debug and intermediate artifact
contracts drift.

## Decision

MacroAgent uses a 9-stage Meal Takeoff Workflow for the v0.3 backend path:

1. Input intake creates a meal case, assigns `trace_id`, and records
   `image_sha256`.
2. Meal classification chooses the high-level meal type.
3. Component takeoff identifies visible and suspected components.
4. Food legend normalization turns observations into normalized food materials.
5. Source seed retrieval collects source candidates.
6. Source critique and revision selects source-backed candidates.
7. Scale Evidence Resolver gathers usable scale evidence.
8. Portion Range Refiner converts evidence into quantity ranges.
9. Macro quantity, gate, trace, and ledger handling recomputes final values and
   decides whether a write is allowed.

The workflow separates agent and deterministic responsibilities. Agents may
produce perception, OCR, critique, or explanation artifacts behind strict
schemas. Deterministic services perform source resolution, arithmetic,
sanity checks, policy decisions, trace persistence, and ledger writes.

Each stage emits an intermediate artifact with a stable schema. Examples include
component claims, source match candidates, scale evidence candidates, portion
ranges, macro intervals, gate decisions, and ledger entries. Stage boundaries
are intentionally narrow: a stage consumes the prior artifact and emits a new
artifact rather than mutating hidden shared state.

Trace instrumentation uses the `TraceEmitter` protocol. Stage code should call
`emit_stage_event` to create a `TraceEvent` at meaningful start, completion,
decision, and error points. The trace boundary is pii-safe: trace records store
`image_sha256` and derived metadata, never raw image bytes or base64 image data.

Scale Evidence Resolver is treated as a substage before Portion Range Refiner.
It decides whether reference objects, saved containers, barcode serving sizes,
manual selections, or other scale candidates can narrow a portion range. Portion
Range Refiner then uses that decision to produce the final range artifact.

## Consequences

The workflow keeps implementation slices testable. A failure in model perception
does not authorize a ledger write, and a deterministic calculator does not need
to know how the source candidate was found. The cost is more schema surface
area, but that surface area is what makes trace review and repair possible.
