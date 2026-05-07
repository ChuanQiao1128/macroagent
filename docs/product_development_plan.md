# MacroAgent Product Development Plan

This plan starts from the current local pipeline state:

- Claude CLI subscription is the default vision provider.
- Local USDA/FDC SQLite matching exists at `local_outputs/fdc_local/nutrition.db`.
- The deterministic nutrition output supports seven user-facing metrics: `kcal`, `protein_g`, `carbs_g`, `fat_g`, `sugar_g`, `sodium_mg`, and `fiber_g`.
- The CLI can run the full estimate path from image or injected vision JSON.

## Product Direction

Current product strategy is single-photo first. Normal users should not be
expected to take multiple angles, photograph menus, or use fixed containers. Those
signals remain optional evidence.

The product should stay split into three layers:

1. Perception: Claude Vision reads the image and returns structured candidates, portion hints, hidden-ingredient risks, and uncertainty.
2. Truth and calculation: local/FDC nutrition matching, portion grams, interval calculation, and ledger persistence stay deterministic.
3. User correction: the app asks only high-impact questions, records corrections, and uses those corrections to improve future portion priors.

Do not put nutrition arithmetic or database facts into the LLM. Use the LLM for uncertain visual understanding and user-facing explanation only.

See [single_photo_product_strategy.md](single_photo_product_strategy.md) for the
current strategy baseline.

## Stage 1: Single-Photo Result Contract

Goal: make one-photo analysis return a useful estimate plus correction hooks.

Build:

- Fast first response for one photo.
- Seven metrics with best/min/max values.
- `quick_corrections` for portion size, hidden sauce/oil, drink add-ins, and amount consumed.
- Confidence and uncertainty drivers.
- Append-only correction capture for future personal priors.

Acceptance:

- User can take or upload one image and receive a result without extra capture steps.
- The result never claims scale-grade precision from a single photo.
- The app asks at most one or two high-impact questions before logging.
- Quick corrections are structured in the backend response and renderable by iOS/web.

## Stage 2: Reliability Before Mobile

Goal: make the one-photo path stable enough for repeated real use.

Build:

- Background worker for analysis jobs; do not run long Claude calls inside the request thread.
- Raw Claude response capture for debugging failed schema parses.
- Vision provider health checks and clear failure categories.
- Timeout budget: first visible UI response under 1 second; final result target under 10-20 seconds when Claude is healthy.
- Cache by normalized image hash, model, prompt hash, and schema version.
- Golden fixture tests for sushi, coffee, rice/chicken, mixed dish with sauce, and failed/blurred image.
- High-impact uncertainty gate: ask user only when estimated impact is meaningful.
- Background second-pass review for difficult mixed meals; do not block the first result with every agent.

Acceptance:

- No terminal-only flow is required for testing.
- Failed Claude calls do not lose uploaded images or user state.
- A full web demo can be replayed from fixtures in under 3 seconds.
- Real Claude calls are isolated behind a job and can be retried.

## Stage 3: Personalization Loop

Goal: turn corrections into better future estimates.

Build:

- User profile defaults: common serving sizes, usual coffee/sugar behavior, common meals.
- Portion correction priors by food class and user.
- Personal catalog editing and confidence flags.
- Meal history and daily totals.
- Correction trace: original estimate, user correction, recalculated estimate.

Acceptance:

- If the user corrects sushi pieces or coffee sugar once, the next similar meal shows a better default.
- High-impact unmatched or hidden components are clearly marked as incomplete until resolved.
- The ledger can explain every number from source food, grams, and calculation version.

## Stage 4: iOS Native App

Goal: move the validated web UX into a mobile-first capture experience.

Build:

- SwiftUI app under `apps/ios`.
- Camera and photo-library upload.
- Analysis job polling against the backend.
- Result cards for the seven metrics.
- Correction screen optimized for thumb input: grams, pieces, cups, sauce toggles, sugar packet toggles.
- Local pending-upload queue for bad network.
- HealthKit export only after result quality is acceptable.

Important boundary:

- iOS should not run Claude, FDC matching, or macro calculation locally in V1.
- iOS should be a capture/review client. Backend remains the source of truth.
- ARKit plate/scale estimation is a later optimization, not a blocker for V1.

Acceptance:

- User can take a meal photo and receive the same backend result as the web app.
- The app can show job progress and recover from slow analysis.
- Corrections sync back to the backend and update the ledger.

## Stage 5: Beta Hardening

Goal: make it safe enough for repeated real use.

Build:

- Auth and user isolation.
- Object storage for images.
- PostgreSQL migration from local SQLite for multi-user use.
- PII and image retention policy.
- Observability for cost, latency, failure rate, retry rate, and correction rate.
- Evaluation dashboard for calibration: p50 accuracy, interval coverage, and high-confidence error rate.

Acceptance:

- A beta user can log meals for a week without manual developer intervention.
- Daily reports show latency, failed jobs, and correction patterns.
- Product decisions are driven by real correction data, not only model confidence.

## Agent Pipeline Gaps

The current agent setup is enough for backend services. Before Web and iOS scale up, it needs tightening:

- Path ACL currently mainly blocks denied paths. It should also enforce allowed paths so each role cannot write outside its ownership.
- There is no dedicated frontend role. Add `frontend_developer` for `apps/web/**` and `frontend_tester` for Playwright/component tests.
- There is no dedicated iOS role. Add `ios_developer` for `apps/ios/**` and an iOS tester role that can run Swift/Xcode checks.
- Tester ACL currently treats all `apps/**` as forbidden. That will block colocated frontend or iOS tests unless we define clear test locations.
- Reviewer model diversity is acceptable in ChatGPT-auth mode, but API/o3 review should be restored when API quota is available.
- Unattended mode should emit a daily summary: tasks run, commits, tests, failures, repair attempts, latency, and unresolved review findings.
- Real Claude CLI smoke tests should be optional and explicit; normal CI should use offline fixtures.

These gaps do not block a web prototype. They do matter before serious iOS work because native apps need separate build tooling, simulator checks, and stricter file ownership.

## Recommended Next Agent Briefs

The first runnable briefs have been created:

1. `TASK-022`: harden Claude CLI vision provider for real subscription calls, raw failure capture, and timeout diagnostics.
2. `TASK-023`: add backend meal-analysis job API with fixture mode.
3. `TASK-024`: scaffold `apps/web` upload/results UI.
4. `TASK-025`: add correction UX and correction persistence through the web flow.

After those pass, create or run the next briefs:

- `TASK-026`: add Playwright smoke tests and screenshots for web.
- `TASK-027`: tighten agent ACL allow enforcement and add frontend/iOS role boundaries. This is a guardrail task and should be human-reviewed, not run as a blind unattended product task.
- `TASK-028`: prepare iOS technical design and SwiftUI skeleton only after Stage 1 web UX is proven.

## Immediate Decision

Keep building the iOS smoke app and backend around single-photo behavior:

- one photo is the default;
- depth, containers, OCR, and menus are optional evidence;
- API responses must carry quick corrections;
- LLMs identify and explain uncertainty but do not calculate final macros;
- multi-agent work should support offline review and hard cases, not every normal request.
