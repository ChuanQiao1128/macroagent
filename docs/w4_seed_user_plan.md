# W4 Seed User Deploy Readiness Plan

This plan prepares MacroAgent for a small paid-product readiness pilot without
waiting for a weighed meal study. W4 validates friction, comprehension, and
logging behavior. W5 separately validates calibration against known or weighed
meals.

## W4 Friction Pilot

Scope:

- 10-20 seed users;
- 1 week;
- normal everyday meals, no requirement to weigh food;
- mobile-first usage if available, otherwise the closest upload/logging flow.

Primary W4 metrics:

- `first_meal_completion`: percentage of users who complete one meal log;
- `time_to_log`: upload/start to ledger decision, median and p95;
- `clarify_trigger_rate`: percentage of meals that ask a clarification;
- `clarify_completion`: percentage of clarification prompts answered;
- `log_anyway_rate`: percentage of CLARIFY cases logged anyway.

Decision criteria:

- W4 can pass even if no weighed meal data exists.
- If `time_to_log` or clarify friction is too high, fix UX and pipeline latency
  before expanding the pilot.
- If users frequently choose log-anyway for the same reason, convert that reason
  into better defaults, saved containers, or clearer portion controls.

## W5 Calibration Pilot

W5 is separate from W4. It measures estimate calibration, not first-use friction.

Scope:

- 5-10 users;
- known meals or weighed meals where possible;
- repeated meals encouraged;
- home meals with kitchen scale are preferred, but labeled packaged food and
  restaurant nutrition proxy meals can be tracked separately.

Primary W5 metrics:

- `correction_within_range`: whether user-corrected or known values fall inside
  `kcal_min` to `kcal_max`;
- repeat meal range shrinkage: change in `relative_range_width` after prior
  corrections or saved container evidence;
- high-confidence miss rate;
- source-backed coverage rate.

W5 outputs should feed benchmark fixtures and policy tuning. They should not
block the W4 deploy-readiness decision.

## Seed User Data Privacy Constraints

Seed-user telemetry must follow these constraints:

- collect the minimum event data needed for the metrics above;
- store trace image references as `image_sha256`, not raw images;
- keep raw meal photos out of trace artifacts;
- avoid collecting health conditions, medical diagnoses, or treatment goals;
- separate user contact details from meal traces and fixture exports;
- ask explicit consent before using a meal as a benchmark fixture;
- anonymize exported examples and remove faces, documents, location clues, and
  unrelated personal objects;
- report aggregate W4/W5 metrics, not individual user behavior.

## Operating Cadence

Review W4 metrics daily during the pilot. Triage failures into latency,
confusing copy, repeated unclear prompts, source matching gaps, and ledger gate
errors. Only after W4 friction is acceptable should the team spend seed-user
time on the W5 known/weighed meal calibration pilot.
