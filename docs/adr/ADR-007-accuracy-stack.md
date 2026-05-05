# ADR-007: Accuracy Stack

Date: 2026-05-05
Status: Accepted

## Context

Accuracy improves through better evidence capture, better calibration, and
personal correction feedback. It should not be treated as a single model upgrade
problem. The system needs measurable release gates so product quality can move
forward without replacing honest uncertainty with overconfident estimates.

## Decision

MacroAgent defines an Accuracy Stack with four layers:

- Information Capture: collect the signals that materially reduce uncertainty,
  including image quality, barcode or label evidence, saved containers,
  clarification answers, and correction events.
- Calibration: compare estimates against fixtures and user corrections to
  measure whether intervals and confidence labels are calibrated.
- Personalization: use saved containers, repeat meal signatures, and correction
  priors to narrow future ranges for the same user.
- Active Learning: choose the single highest-value clarification or retake prompt
  only when it can materially improve the estimate.

Release gates are numeric:

- Gate 1 target: at least 90% of source-backed fixture meals produce a valid
  `relative_range_width` and non-empty `confidence_label`.
- Gate 2 threshold: no more than 10% of accepted fixture meals may have a known
  correction outside the stored calorie interval.
- Gate 3 max: at most 1 clarification question in the default logging path.
- Gate 4 target: at least 70% of repeat-meal corrections should narrow the next
  interval compared with the cold estimate.

Ablation evaluation must isolate which evidence source changed the result. Each
ablation run disables one source family, such as saved containers, barcode
serving evidence, personal priors, or hidden-ingredient policy defaults, and
compares interval width, correction error, and clarify rate.

Cold-start behavior uses First 3 Meals Calibration Mode. During the first 3
logged meals, the app should encourage portion correction, container selection,
or a quick confirmation when the benefit is high. After those meals, the product
should rely more on stored priors and ask fewer questions.

Weekly uncertainty debt is the backlog of logged entries whose interval was wide
or whose primary driver was unresolved. It should be summarized by reason, such
as missing scale reference, sauce amount unknown, or source mismatch. The weekly
review should favor corrections that improve future estimates, not merely
retroactive bookkeeping.

## Consequences

This keeps accuracy work measurable. Model changes, policy changes, and personal
learning can each be evaluated independently, and a release can be blocked when
calibration worsens even if the default screen still looks plausible.
