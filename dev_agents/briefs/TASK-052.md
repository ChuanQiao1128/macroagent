# TASK-052 - iOS User Result UI v1

## Goal

Turn the iOS smoke app result screen into a user-facing single-photo nutrition
result experience while keeping the debug view available.

## Product value

The phone test should look like an early product, not only a backend contract
debugger. Users should see the seven key metrics, estimate ranges, confidence,
and quick corrections in a readable way.

## Scope

Implementation may modify:

- `apps/ios/**`

Tester may add:

- `tests/ios/**`

Doc role may update:

- `docs/**`

## Requirements

- Build a user-facing result screen for:
  - `kcal`
  - `protein_g`
  - `carbs_g`
  - `fat_g`
  - `sugar_g`
  - `sodium_mg`
  - `fiber_g`
- Show best estimate and range without overclaiming precision.
- Show status: `ACCEPT`, `WARN`, `CLARIFY`, or `BLOCK`.
- Show high-impact uncertainty drivers and at most one or two primary questions.
- Render quick correction buttons or controls for portion, amount consumed,
  sauce/oil, and drink add-ins when present.
- Move raw request/response details into a secondary Debug view.
- Keep all model calls and nutrition calculation on the backend.

## Acceptance criteria

- Static or Swift tests verify the user result screen references all seven
  metrics and quick correction actions.
- iOS build succeeds with code signing disabled.
- Existing Result Debug still exists for developer troubleshooting.
- Manual runbook explains how to install on iPhone and test against the local
  Mac server.
- Existing full test suite remains green.

## Commands

- `pytest -p no:cacheprovider tests/ios`
- `ruff check tests/ios`
- `xcodebuild -project apps/ios/MacroAgentCapture.xcodeproj -scheme MacroAgentCapture -destination 'generic/platform=iOS' CODE_SIGNING_ALLOWED=NO build`

## Forbidden

- Do not add production login.
- Do not call Anthropic/OpenAI from iOS.
- Do not add App Store/TestFlight work.
- Do not edit `.codex/**`, `.github/**`, `dev_agents/policies/**`,
  `evals/golden_set/**`, `prompts/**`, or `DESIGN_zh*.md`.
