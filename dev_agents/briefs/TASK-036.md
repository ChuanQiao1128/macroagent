# TASK-036 — Benchmark Fixtures

## Goal

Add fixture coverage for v0.3 gates.

## Fixture groups

```text
friendly
regression
adversarial
scale_evidence
cross_cultural
barcode_label_stub
```

## Required fixtures

Scale evidence:

```text
1. no_reference_low_impact
2. no_reference_high_impact_bowl
3. spoon_visible_near_plate
4. fork_visible_far_from_plate
5. saved_bowl_detected
6. barcode_packaged_food
7. card_like_object_with_pii
8. plate_visible_unknown_size
```

Energy density:

```text
1. cooked rice correct density
2. dry rice incorrectly used for cooked rice
3. sauce mapped to oil
4. mixed bowl aggregate passes but component fails
```

Evidence arbitration:

```text
1. compatible portion ranges merge
2. incompatible macro values conflict
3. user correction beats default prior
4. LLM raw macro blocks
```

## Acceptance criteria

- Benchmark report separates friendly/regression/adversarial results.
- Silent high conflict rate is measured.
- CLARIFY trigger distribution is reported.
- Tests pass.

---
