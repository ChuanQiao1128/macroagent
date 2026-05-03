# MacroAgent Project Context

## What This Product Is

A confidence-aware nutrition accounting agent. Outputs best-estimate, range,
and source for every meal instead of a single hidden-uncertainty number.

## Architecture

- Backend: FastAPI and Python 3.12.
- Product agent orchestration: LangGraph for MealAnalysisGraph only.
- Dev agent orchestration: Codex CLI roles, Python queue, and GitHub Actions.
- RAG: Chroma for V0-V1, then pgvector for V2.
- Frontend: React, TypeScript, and Tailwind for the V0.5 web demo.
- iOS V1: SwiftUI, ARKit, and HealthKit.

## Where To Find Things

- Product spec: DESIGN_zh.md. Read-only for all agents.
- Prompts: prompts/**. Read-only except for the human owner.
- Golden set: evals/golden_set/**. Read-only for all agents.
- Path ACL rules: dev_agents/policies/path_acl.yaml.
- Per-role boundaries: .codex/roles/<role>.md.

## Hard Rules

- Never modify DESIGN_zh*.md.
- Never modify prompts/** unless role=human.
- Never modify evals/golden_set/** unless role=human.
- Never modify .codex/**, .github/**, or dev_agents/policies/** from an agent task.
- Never use Swift force unwraps.
- Always include weak self handling in escaping Swift closures.
- Never approve your own work.
- If a task needs a forbidden path, stop and escalate instead of working around the rule.
