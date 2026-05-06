# TASK-047 - Phone-to-Mac End-to-End Smoke Test

## Goal

Wire the iOS app to the local Mac server and document a real-device smoke test.

## Product value

This task should let the user take a photo on an iPhone, send metadata to the Mac,
and see a backend response on the phone.

## Scope

Implementation may modify:

- `apps/ios/**`
- `services/api/**` only for tiny compatibility fixes

Tester may add:

- `tests/ios/**`
- `tests/api/**`

Doc role may update:

- `docs/**`

## Requirements

- Add API client code for `POST /v1/meals/analyze-photo`.
- Show request metadata preview before sending.
- Show response status, reasons, trace ID, seven nutrition metrics, and clarify
  questions when present.
- Add error states for invalid server URL, network failure, and invalid response.
- Add manual smoke-test runbook:
  - find Mac LAN IP;
  - start local server;
  - configure iPhone server URL;
  - take photo;
  - send request;
  - verify response.
- Keep mock-first backend behavior explicit.

## Acceptance criteria

- Static tests verify API client endpoint, result fields, and runbook commands.
- App code references the v0.4 contract field names.
- Runbook includes troubleshooting for same-Wi-Fi/LAN access and macOS firewall.
- Existing full test suite remains green.

## Commands

- `pytest tests/ios/ tests/api/`
- `ruff check tests/ios tests/api services/api`

## Forbidden

- Do not add production auth.
- Do not call Anthropic/OpenAI from the iOS app.
- Do not store real photos in the repo.
- Do not edit `.codex/**`, `.github/**`, `dev_agents/policies/**`,
  `evals/golden_set/**`, `prompts/**`, or `DESIGN_zh*.md`.
