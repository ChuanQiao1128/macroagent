# MacroAgent Single-Photo Product Strategy

## Decision

MacroAgent should assume the normal user takes one meal photo. Multi-angle
capture, menus, known containers, and reference objects are optional evidence,
not the default user flow.

The product should therefore optimize for:

- fast first estimate;
- honest nutrition ranges;
- one or two high-impact questions only when needed;
- quick correction controls;
- personal learning from repeated corrections.

It should not position single-photo analysis as scale-grade weighing.

## Product Loop

```text
single photo
-> structured vision component candidates
-> deterministic nutrition/source matching
-> portion interval from food type, visible count, depth if available, and priors
-> deterministic seven-metric nutrition calculation
-> quick corrections for high-impact uncertainty
-> append-only ledger and personal prior update
```

## Runtime Strategy

The first response should be lightweight:

- run one vision pass;
- avoid multi-agent debate on the critical path;
- compute deterministic nutrition from source-backed data;
- return best/min/max values and quick corrections;
- defer deeper review to background or difficult cases.

Multi-agent work is still useful, but mostly for:

- offline evaluation;
- template generation for common dishes;
- error review;
- high-risk second-pass arbitration;
- improving retrieval and correction priors.

It should not run every possible agent for every photo.

## Error Reduction Without Extra Photos

The system reduces single-photo error by combining small evidence signals:

- food category-specific portion priors;
- visible piece count for discrete foods;
- common dish templates for mixed meals;
- ARKit/depth metadata when available;
- OCR/barcode when visible;
- hidden sauce, oil, sugar, and cream risk detection;
- user correction history.

The highest-value questions are those that change the result materially, such as
portion size, hidden sauce/oil, drink add-ins, and amount consumed.

## User-Facing Result

The user should see:

- seven nutrition metrics;
- a reasonable range;
- a confidence label;
- the main uncertainty drivers;
- quick correction controls.

The first mobile implementation may expose these in debug form, but the contract
already carries them as structured fields:

- `quick_corrections` in the response tells the client which controls to render;
- `options.quick_correction_selections` in the next request tells the backend
  which options the user selected;
- the backend recomputes nutrition deterministically from source-backed entries
  and fixed portion/correction rules.
