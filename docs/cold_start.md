# Cold Start and First 3 Meals Calibration Mode

MacroAgent v0.3 treats the first three logged meals as a calibration period. The
goal is not to prove final calorie accuracy immediately; the goal is to capture
just enough user-specific evidence to make later logging faster and more
trustworthy.

## First 3 Meals Calibration Mode

First 3 Meals Calibration Mode applies to a new user until three meals have been
logged or intentionally skipped. During this mode the product may ask for one
high-value calibration action when it materially reduces uncertainty:

- choose a saved bowl, plate, cup, or common container;
- correct a portion estimate in grams, cups, pieces, or servings;
- confirm whether visible sauce, oil, cream, or dressing was present;
- confirm the primary food identity when top candidates are materially different;
- choose log-anyway when the user wants speed over narrowing the range.

The mode must preserve the normal logging path. A user can always log anyway
with a wide range, and the ledger must carry `user_accepted_wide_range=True`
when that happens.

## Data Captured

The cold-start path may store:

- meal signature hash;
- normalized component names and categories;
- portion correction priors;
- saved container identifiers;
- clarify prompts shown and answered;
- `relative_range_width` before and after any correction;
- final `confidence_label`;
- trace id and version matrix references.

The cold-start path must not store raw meal images in trace artifacts. Trace
events may store `image_sha256` and derived non-image metadata only.

## Success Metrics

Cold-start success is measured by:

- first three meal completion rate;
- median and p95 time to log;
- clarify trigger rate;
- clarify completion rate;
- log-anyway rate;
- reduction in `relative_range_width` on repeated foods or saved containers.

## Product Rule

First 3 Meals Calibration Mode is allowed to increase helpful prompts during
meals one through three, but after that the product should rely on the captured
priors and ask fewer questions. Calibration work should improve future logging,
not turn every meal into a survey.
