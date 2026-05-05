# ADR-005: Ranged Estimate Ledger Policy

Date: 2026-05-05
Status: Accepted

## Context

Photo-based nutrition logging cannot justify fake single-number precision.
Portion estimation from one image is noisy, and the largest errors usually come
from bowl size, hidden oil or sauce, raw-vs-cooked confusion, and partial
consumption. The product therefore stores a best estimate with explicit range
metadata instead of pretending the midpoint is exact.

## Decision

MacroAgent uses a ranged estimate policy for ledger writes.

Each source-backed meal estimate stores min/best/max values as `kcal_min`,
`kcal_best`, and `kcal_max`. Optional macro fields may follow the same shape for
protein, carbs, and fat, but calories are the required interval for gate
decisions.

The ledger best estimate vs range metadata rule is:

- `kcal_best` is the value used for daily totals and default display.
- `kcal_min` and `kcal_max` stay attached to the entry for review, uncertainty
  debt, and correction learning.
- min/best/max storage must remain source-backed and recomputable from source
  nutrition values and portion ranges.

The component aggregation method is `component_mode_sum`: the system sums each
component's min, best, and max directly. This is practical for v0.3 but is not a
true joint statistical mode. The caveat must remain visible in calculator
docstrings and later product trace views.

The ledger is append-only. Corrections create new active rows and supersede old
rows; old rows remain for audit. Every ledger entry carries a version matrix,
currently represented by `LedgerVersionMatrix`, so future recalculation can
explain which calculator, policy, source dataset, and pipeline version produced
the entry.

CLARIFY and log-anyway behavior is explicit:

- `ACCEPT` and `WARN` entries may write normally.
- `CLARIFY` does not auto-write by default.
- If the user chooses log-anyway, write a low-confidence entry with
  `user_accepted_wide_range=True`.
- If the user selected a reason, store `user_decline_clarify_reason` using the
  shared allowed reason codes.
- `BLOCK` remains reserved for contract violations and never writes.

## Consequences

This design makes portion estimation accuracy reality visible without forcing
the normal user path to become complex. Users can log quickly, but the ledger
does not lose the uncertainty context needed for weekly review, correction
loops, and future recalculation.

The tradeoff is that downstream summaries must distinguish `kcal_best` totals
from range metadata. Product surfaces should not imply that the best estimate is
more precise than the stored interval supports.
