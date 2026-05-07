# TASK-057 - User History, Daily Totals, and HealthKit Export Prep

## Goal

Add local user meal history, daily nutrition totals, and a HealthKit export
contract for future iOS integration.

## Product value

Users do not only need one estimate. They need to see what they ate today, review
past meals, and eventually export accepted nutrition entries to Apple Health.

## Scope

Implementation may modify:

- `services/api/**`
- `services/capture/**`
- `services/meal/**`
- `services/nutrition/**`
- `services/storage/**`
- `apps/ios/**`

Tester may add:

- `tests/api/**`
- `tests/capture/**`
- `tests/meal/**`
- `tests/nutrition/**`
- `tests/storage/**`
- `tests/ios/**`

Doc role may update:

- `docs/**`

## Requirements

- Add local user-scoped meal history APIs or storage accessors.
- Add daily totals for the seven core metrics:
  - `kcal`
  - `protein_g`
  - `carbs_g`
  - `fat_g`
  - `sugar_g`
  - `sodium_mg`
  - `fiber_g`
- Daily totals must use accepted or corrected deterministic ledger entries only.
- Add a HealthKit export preparation schema that maps accepted nutrition entries
  to HealthKit-compatible quantities.
- iOS may show a simple history or daily total screen if the existing app
  structure supports it.
- Do not add production HealthKit entitlements unless they can be implemented
  and tested safely in this task.
- Emit TraceEvents for ledger-to-history and HealthKit export preparation.

## Acceptance criteria

- Tests prove daily totals aggregate only the current user and selected day.
- Tests prove corrected entries supersede original estimates in totals without
  mutating the append-only correction history.
- Tests prove HealthKit export prep includes all supported quantities and skips
  unavailable values explicitly.
- iOS static tests or build checks cover any new user-facing history/totals UI.
- Existing full test suite remains green.

## Commands

- `pytest -p no:cacheprovider tests/api tests/capture tests/meal tests/nutrition tests/storage tests/ios`
- `ruff check services/api services/capture services/meal services/nutrition services/storage tests/api tests/capture tests/meal tests/nutrition tests/storage tests/ios`
- `xcodebuild -project apps/ios/MacroAgentCapture.xcodeproj -scheme MacroAgentCapture -destination 'generic/platform=iOS' CODE_SIGNING_ALLOWED=NO build`

## Forbidden

- Do not add production auth.
- Do not add cloud sync.
- Do not write to Apple Health automatically.
- Do not edit `.codex/**`, `.github/**`, `dev_agents/policies/**`,
  `evals/golden_set/**`, `prompts/**`, or `DESIGN_zh*.md`.
