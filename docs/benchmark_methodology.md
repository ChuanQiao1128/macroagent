# Benchmark and Ablation Methodology

MacroAgent benchmarks are designed to measure evidence quality, deterministic
policy behavior, latency, and calibration without letting an LLM invent final
nutrition values.

## Fixture Families

The v0.3 fixture plan includes:

- cross-cultural food identity and component normalization fixtures;
- scale evidence fixtures for reference objects, saved containers, labels, and
  manual choices;
- hidden ingredient and unknown component fixtures;
- ledger gate fixtures for ACCEPT, WARN, CLARIFY, BLOCK, and log-anyway.

Golden or weighed meals belong to the W5 calibration pilot. W4 deploy readiness
does not require weighed meals.

## Factorial Ablation Design

Ablation must use factorial design, not only single main effects. The default
factors are binary switches:

- `vision_top_k`: on/off;
- `source_critic`: on/off;
- `scale_evidence`: on/off;
- `personal_priors`: on/off;
- `uncertainty_gate`: on/off.

For five binary factors, the full factorial design has 2^5 = 32 cells. Each cell
records the same fixture ids and metrics so interactions can be measured. For
example, scale evidence and personal priors may each help alone but have a
larger combined effect on repeat meals.

Minimum ablation metrics:

- interval coverage when ground truth is available;
- `relative_range_width`;
- `confidence_label` calibration;
- clarify trigger rate;
- log-anyway rate;
- source-backed coverage;
- latency p50 and p95.

The helper script `evals/run_ablation.py` generates factorial cells and can
summarize JSONL fixture results without requiring model calls.

## Integration Smoke Pipeline

TASK-037 adds a deterministic mock integration smoke pipeline that exercises the
end-to-end local control flow without any LLM or network calls. The fixture
sequence is:

- `MealCase` mock input;
- mock `ComponentTakeoff` output;
- mock `SourceSeed` candidates;
- mock `SourceCritic` result;
- mock `ScaleEvidenceResolution`;
- `PortionRange`;
- `MacroQuantity`;
- `EvidenceArbitration`;
- `LedgerGate`;
- `TraceStore`;
- `LedgerEntry`.

The smoke suite includes one fixture each for `ACCEPT`, `WARN`, `CLARIFY`
with log-anyway enabled, and `BLOCK` for an unsupported raw LLM macro claim.
Every stage emits trace events, and written ledger entries carry the version
matrix required for auditability.

## Latency Budgets

```yaml
latency_budgets_v0_3:
  contract_guard_layers_1_to_4:
    p95_ms: 25
  evidence_arbitration:
    p95_ms: 50
  takeoff_full_pipeline_sync_without_cloud_vision:
    p95_ms: 200
  takeoff_async_path:
    sla: none
```

Latency gates should be evaluated separately from cloud vision latency. Cloud
vision belongs to asynchronous or provider-specific measurement; the local
deterministic path should remain fast enough for responsive product feedback.

## Reporting

Every benchmark report should include:

- fixture family and version;
- enabled ablation factors;
- number of meals or components evaluated;
- source-backed coverage;
- interval and confidence metrics;
- latency budget pass/fail;
- known limitations and excluded fixture families.
