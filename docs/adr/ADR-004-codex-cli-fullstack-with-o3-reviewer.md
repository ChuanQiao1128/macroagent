# ADR-004: Codex CLI Fullstack With o3 Reviewer

Date: 2026-05-03
Status: Accepted

## Context

MacroAgent needs a human-supervised autonomous development pipeline that can
move implementation work quickly without letting one agent validate its own
output. The main risks are self-validation, prompt or golden-set contamination,
architecture drift, and runaway model spend.

Using multiple tools would increase operational complexity during V0. A single
Codex CLI workflow is simpler to install, observe, and teach. The downside is
echo chamber risk if every role uses the same model family and the Reviewer
shares the Developer's blind spots.

## Decision

Use Codex CLI for the development pipeline and enforce model diversity by role:

- Developer, Tester, and Bug Fixer use gpt-5-codex.
- Reviewer uses o3 and runs read-only.
- Doc uses gpt-5-mini.

The Reviewer must not write source or approve its own work. Deterministic
guardrails remain mandatory: path ACL, tests, eval gates, CODEOWNERS, branch
protection, and cost monitoring.

## Consequences

This keeps the day-zero tooling surface small while reducing single-model
review risk. The remaining risk is handled by hard gates and human review for
sensitive paths, especially DESIGN_zh*.md, prompts/**, evals/golden_set/**,
docs/adr/**, .codex/**, .github/**, and dev_agents/policies/**.

If V1 SwiftUI or camera-heavy work shows persistent model-specific failure
patterns, the team can revisit whether to add a second coding tool. Until then,
the pipeline stays single-tool with model diversity.
