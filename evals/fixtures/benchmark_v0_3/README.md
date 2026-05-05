# TASK-036 Benchmark Fixture Results (v0.3)

This fixture set provides one canonical benchmark result row for each required
v0.3 gate fixture in TASK-036. The catalog in `services.meal` also carries
the executable gate inputs used to regenerate the same outcomes.

Files:

- `task_036_fixture_results.jsonl`: canonical result rows used by tests and
  benchmark report validation.

Coverage:

- Segments: `friendly`, `regression`, `adversarial` (derived from fixture id);
- Families: `scale_evidence`, `cross_cultural`, `barcode_label_stub`;
- Gates: `scale_evidence`, `energy_density`, `evidence_arbitration`.
- Executable regression cases: missing-scale CLARIFY, density-outlier CLARIFY,
  macro-conflict CLARIFY, and llm-raw macro BLOCK.
- CLARIFY distribution includes trigger-cause buckets such as `missing_scale`,
  `density_outlier`, and `macro_conflict`.

Validation command:

```bash
python -m services.cli.benchmark_report \
  --fixtures-jsonl evals/fixtures/benchmark_v0_3/task_036_fixture_results.jsonl
```
