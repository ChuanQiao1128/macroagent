# TASK-032 — Range and Sanity Policy

## Goal

Implement ranged estimate core, uncertainty policy, CLARIFY gate, energy-density sanity checks, and log-anyway behavior.

## Files to create / update

```text
services/meal/policies/uncertainty_policy.yaml
services/meal/policies/energy_density_policy.yaml
services/meal/policies/scale_evidence_policy.yaml
services/meal/takeoff/portion_refiner.py
services/meal/takeoff/macro_quantity.py
services/meal/takeoff/ledger_gate.py
services/meal/takeoff/energy_density.py
tests/meal/takeoff/test_range_calculator.py
tests/meal/takeoff/test_clarify_gate.py
tests/meal/takeoff/test_energy_density.py
```

## Requirements

1. Implement component interval macro calculation:
   - min/best/max kcal
   - optional protein/carbs/fat min/best/max
2. Aggregate meal min/best/max by component sum.
3. Add component_mode_sum caveat in docstring and ADR later.
4. Implement relative range width:
   - <=0.35 ACCEPT
   - >0.35 and <=0.60 WARN
   - >0.60 CLARIFY
5. BLOCK still reserved for contract violations.
6. Implement per-component energy density check.
7. Implement per-meal aggregate energy density check.
8. Implement log-anyway behavior:
   - creates low-confidence ledger entry
   - sets `user_accepted_wide_range=True`
9. Unknown component bounds must come from `uncertainty_policy.yaml`, never hardcoded in calculator.

## Acceptance criteria

- Visible unknown sauce lower bound is not zero if policy says visible.
- Suspected hidden oil may have lower bound zero.
- Right-skewed component preserves distribution_shape/skew_hint.
- CLARIFY does not auto-write ledger unless log-anyway selected.
- Energy density per-component outlier emits warning/block/clarify decision.
- Mixed meal does not false-positive solely on meal aggregate if components pass.
- Tests pass.

## Out of scope

- Monte Carlo weekly summary
- full reference object geometry
- real source data lookup

---
