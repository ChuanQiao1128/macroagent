# TASK-043 - Local Analyze Photo HTTP Server

## Goal

Expose the existing analyze photo facade through a local HTTP server that an
iPhone on the same network can call.

## Product value

This is the first step toward a real phone smoke test. The backend must accept a
v0.4 capture request over HTTP and return a deterministic analysis response.

## Scope

Implementation may modify:

- `services/api/**`
- `services/cli/**` if a CLI entrypoint is useful

Tester may add:

- `tests/api/**`
- `tests/cli/**`

Doc role may update:

- `docs/**`

## Requirements

- Use Python standard library HTTP server unless a server framework already exists.
- Add `python -m services.api.local_server --host 0.0.0.0 --port 8765`.
- Implement `GET /health`.
- Implement `POST /v1/meals/analyze-photo`.
- Accept JSON matching `AnalyzePhotoFacadeRequest` or raw `PhotoAnalyzeRequest`.
- Return JSON matching `AnalyzePhotoFacadeResponse`.
- Return structured JSON errors for invalid JSON, invalid schema, unsupported path,
  and unsupported method.
- Do not add live LLM/model calls.
- Do not store raw image bytes.

## Acceptance criteria

- Unit tests cover health, valid analyze request, invalid JSON, invalid schema, and
  unsupported path.
- Response includes `trace_id`, `status`, nutrition or block reason, and no raw image
  fields.
- Server can be started with the documented module command.
- Existing full test suite remains green.

## Commands

- `pytest tests/api/ tests/cli/`
- `ruff check services/api services/cli tests/api tests/cli`

## Forbidden

- Do not add FastAPI/Flask unless already present.
- Do not open public network services by default in tests.
- Do not edit `.codex/**`, `.github/**`, `dev_agents/policies/**`,
  `evals/golden_set/**`, `prompts/**`, or `DESIGN_zh*.md`.
