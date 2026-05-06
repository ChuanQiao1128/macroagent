# TASK-044 - iOS SwiftUI Project Skeleton

## Goal

Create a minimal native iOS SwiftUI app skeleton for the MacroAgent capture smoke
test.

## Product value

The user needs to run a real iPhone app that can eventually take a photo and call
the local Mac backend. This task lays down the native app structure and runbook.

## Scope

Implementation may modify:

- `apps/ios/**`

Tester may add:

- `tests/ios/**`

Doc role may update:

- `docs/**`

## Requirements

- Add app source under `apps/ios/MacroAgentCapture`.
- Include SwiftUI entrypoint, root view, capture screen placeholder, metadata preview
  placeholder, and result/debug view placeholder.
- Include a lightweight networking client abstraction for the local server URL.
- Include a README explaining how to create/open the Xcode project if the repo does
  not generate one automatically.
- Keep the app code self-contained and deterministic.
- Do not require third-party Swift packages.

## Acceptance criteria

- Static tests verify required Swift files exist.
- README documents minimum iOS version, required capabilities, and local server URL.
- Source contains clear seams for capture service, metadata builder, API client, and
  result view.
- Existing Python tests remain green.

## Commands

- `pytest tests/ios/`
- `ruff check tests/ios`

## Forbidden

- Do not implement camera capture yet.
- Do not add external Swift package dependencies.
- Do not edit `.codex/**`, `.github/**`, `dev_agents/policies/**`,
  `evals/golden_set/**`, `prompts/**`, or `DESIGN_zh*.md`.
