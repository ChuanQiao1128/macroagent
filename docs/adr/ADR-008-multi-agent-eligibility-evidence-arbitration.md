# ADR-008: Multi-Agent Eligibility and Evidence Arbitration

Date: 2026-05-05
Status: Accepted

## Context

Multiple model roles can help only when they introduce independent evidence.
Using several agents to debate the same photo or the same calorie number creates
correlated failure modes and can make estimates look more reliable than they
are.

## Decision

Agent eligibility rule: add a model role only when it creates, extracts, or
critiques a distinct evidence source that a deterministic layer can validate.

Approved multi-agent positions are:

- vision or OCR extraction behind strict schemas;
- semantic source critique when source candidates conflict;
- structured explanation after deterministic values are already computed;
- reviewer roles for development work, operating read-only.

Rejected multi-agent patterns are:

- using several LLMs to vote on a final calorie, kcal, or macro number;
- letting a model overwrite source nutrition values;
- letting a model bypass deterministic macro arithmetic;
- using model consensus as a substitute for source provenance;
- allowing a writer role to approve its own output.

The Evidence Arbitration Layer resolves claims after extraction. It operates on
typed `EvidenceClaim` payloads and never on untyped dict values. The rule is
compatibility before conflict: compatible portion ranges merge before any
conflict is raised.

Per-claim arbitration is used because identity, portion, macro source, scale
evidence, and consumption fraction have different metrics. Current conflict
metrics include:

- `range_overlap` for portion ranges;
- `relative_diff:kcal` for macro value disagreement;
- `category_jaccard` for food identity category mismatch.

Conflict resolution order is:

1. validate schemas and reject malformed claims;
2. group by claim type and component id;
3. apply compatibility rules;
4. detect conflicts by metric threshold;
5. prefer higher-quality deterministic or user-confirmed sources;
6. ask the user only when the unresolved conflict materially affects the result;
7. block ledger writes for contract violations.

Cross-cultural component normalization is handled before source selection. The
normalizer should preserve cuisine tags, aliases, preparation state, and
regional source relevance so that foods are not forced into the wrong generic
category too early.

## Consequences

This rejects LLM voting for calories/macros and keeps final numbers governed by
source-backed deterministic recomputation. More roles are acceptable only when
they improve evidence diversity or review quality; role count itself is not a
product feature.
