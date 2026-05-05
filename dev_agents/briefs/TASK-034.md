# TASK-034 — W4 Deploy Readiness Design

## Goal

Prepare deploy-readiness and seed-user measurement design without blocking W3 implementation.

## Files to create / update

```text
docs/cold_start.md
docs/w4_seed_user_plan.md
docs/benchmark_methodology.md
evals/fixtures/cross_cultural/README.md
evals/fixtures/scale_evidence/README.md
evals/run_ablation.py
```

## Requirements

1. Define First 3 Meals Calibration Mode.
2. Define W4 friction pilot:
   - 10–20 users
   - 1 week
   - first_meal_completion
   - time_to_log
   - clarify_trigger_rate
   - clarify_completion
   - log_anyway_rate
3. Define W5 calibration pilot separately:
   - 5–10 users
   - known meals / weighed meals where possible
   - correction_within_range
   - repeat meal range shrinkage
4. Define cross-cultural fixture set:
   - zh, vi, th, ja, ko, hi/ur
5. Define factorial ablation methodology.
6. Define latency budgets:

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

7. Define seed user data privacy constraints.

## Acceptance criteria

- W4 deploy plan does not depend on weighed meal study.
- W5 golden / weighed meal study is separate.
- Ablation plan includes factorial design, not only single main effects.
- Cross-cultural fixture README lists minimum examples.
- Latency budget is documented.

---
