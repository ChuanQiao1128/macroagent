# MacroAgent Product Development Plan

This plan starts from the current local pipeline state:

- Claude CLI subscription is the default vision provider.
- Local USDA/FDC SQLite matching exists at `local_outputs/fdc_local/nutrition.db`.
- The deterministic nutrition output supports seven user-facing metrics: `kcal`, `protein_g`, `carbs_g`, `fat_g`, `sugar_g`, `sodium_mg`, and `fiber_g`.
- The CLI can run the full estimate path from image or injected vision JSON.

## Product Direction

The product should stay split into three layers:

1. Perception: Claude Vision reads the image and returns structured candidates, portion hints, hidden-ingredient risks, and uncertainty.
2. Truth and calculation: local/FDC nutrition matching, portion grams, interval calculation, and ledger persistence stay deterministic.
3. User correction: the app asks only high-impact questions, records corrections, and uses those corrections to improve future portion priors.

Do not put nutrition arithmetic or database facts into the LLM. Use the LLM for uncertain visual understanding and user-facing explanation only.

## Stage 1: Web Testing Shell

Goal: make the product testable by a human in a browser before building mobile.

Build:

- FastAPI endpoint for meal analysis jobs.
- React/Tailwind web app under `apps/web`.
- Upload image screen.
- Job progress states: `queued`, `running_vision`, `matching`, `needs_confirmation`, `complete`, `failed`.
- Result screen showing the seven metrics, range, matched foods, portion estimates, and uncertainty.
- One-click correction controls for grams, pieces, sugar packet used/not used, sauce/mayo yes/no.
- Local SQLite persistence for jobs, images metadata, estimates, and corrections.

Acceptance:

- User can upload `sushi.jpg` or `coffee.jpg` from the browser.
- UI returns a result without opening terminal.
- If Claude CLI is slow or fails, the job remains visible with a recoverable status.
- Offline fixture mode can replay `local_outputs/sushi_vision.json` and `local_outputs/coffee_vision.json` for frontend demos without spending model calls.

Why Web first:

- Faster iteration than iOS.
- Easier to debug the analysis trace.
- Lets us validate the correction UX before committing to native mobile flows.
- Playwright can protect the UI cheaply in CI.

## Stage 2: Reliability Before Mobile

Goal: make the analysis path stable enough that a mobile client can depend on it.

Build:

- Background worker for analysis jobs; do not run long Claude calls inside the request thread.
- Raw Claude response capture for debugging failed schema parses.
- Vision provider health checks and clear failure categories.
- Timeout budget: first visible UI response under 1 second; final result target under 15-30 seconds when Claude is healthy.
- Cache by normalized image hash, model, prompt hash, and schema version.
- Golden fixture tests for sushi, coffee, rice/chicken, mixed dish with sauce, and failed/blurred image.
- High-impact uncertainty gate: ask user only when estimated impact is meaningful.

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

Build Web first. Do not start iOS native until the browser flow proves:

- upload works,
- results are understandable,
- hidden uncertainty can be corrected,
- the backend job model handles slow Claude calls,
- and the seven-metric output is stable across fixture and real runs.

Starting iOS before that would mostly move uncertainty into Swift code and slow down iteration.
