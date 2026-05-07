# MacroAgent v0.6 Product Completion Runbook

This runbook turns the current product gaps into an unattended Codex CLI queue.
It is intentionally sequential because later tasks depend on earlier backend and
iOS contracts.

## Queue

The default queue is:

1. `TASK-050` - Real Vision Job Provider and Image Intake
2. `TASK-051` - Background Analysis Job Queue
3. `TASK-052` - iOS User Result UI v1 (verified in `apps/ios/MacroAgentCapture` and `tests/ios/test_task_052_ios_user_result_ui_static.py`)
4. `TASK-053` - Correction Persistence and Personal Priors
5. `TASK-054` - Image Privacy, Cache, and Retention Policy
6. `TASK-055` - Real Food Evaluation Fixtures
7. `TASK-056` - Dish Template and RAG Seed Layer
8. `TASK-057` - User History, Daily Totals, and HealthKit Export Prep

## Dry Run

Use this to prove the script can find every brief before starting agents:

```bash
cd /Users/qc/Documents/Claude/Projects/NutritionAI
V06_DRY_RUN=1 bash scripts/run_product_completion_until_done.sh
```

## Unattended Run

Use this command when Codex CLI is installed and authenticated. It is designed
for an overnight run: each task gets the normal repair loop, and if a task still
fails after the repair limit, the runner records it and continues to the next
task.

```bash
cd /Users/qc/Documents/Claude/Projects/NutritionAI
CODEX_PROVIDER_MODE=chatgpt MAX_REPAIR_ATTEMPTS=5 UNATTENDED_MODE=branch AUTO_PUSH=1 \
  V06_AUTOSTASH=1 V06_CONTINUE_ON_FAILURE=1 \
  caffeinate -dimsu bash scripts/run_product_completion_until_done.sh
```

The script writes progress to:

```text
.codex/runs/product_completion_v06_state.tsv
```

If a task exhausts repairs, its branch and any dirty failure state are preserved,
the task is recorded as `FAILED`, and the queue continues. The script exits with
status `1` at the end if any task failed. Rerun the same command to retry failed
tasks; completed tasks are skipped unless `RERUN_COMPLETED=1` is set.

When `V06_AUTOSTASH=1`, pre-existing dirty worktree files are saved before the
queue starts so `.codex/scripts/run_unattended.sh` can run from a clean tree.
Inspect saved stashes with:

```bash
git stash list | grep macroagent-v06
```

## Single Task Run

To run only part of the queue:

```bash
cd /Users/qc/Documents/Claude/Projects/NutritionAI
CODEX_PROVIDER_MODE=chatgpt MAX_REPAIR_ATTEMPTS=5 UNATTENDED_MODE=branch AUTO_PUSH=1 \
  bash scripts/run_product_completion_until_done.sh TASK-050 TASK-051
```

## Boundaries

- iOS remains a capture and review client.
- Backend remains the source of truth for vision orchestration, FDC matching,
  portion estimation, and nutrition calculation.
- LLM/model outputs must stay behind strict schemas.
- Final calories and macros must come from deterministic recomputation.
- Raw meal images must not be stored in trace artifacts, ledger rows, committed
  fixtures, or agent run outputs.
