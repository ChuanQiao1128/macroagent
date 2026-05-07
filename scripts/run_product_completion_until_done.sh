#!/usr/bin/env bash
# Run the v0.6 product completion queue until all selected tasks finish.
#
# Default queue:
#   TASK-050 TASK-051 TASK-052 TASK-053 TASK-054 TASK-055 TASK-056 TASK-057
#
# Usage:
#   CODEX_PROVIDER_MODE=chatgpt MAX_REPAIR_ATTEMPTS=3 \
#     bash scripts/run_product_completion_until_done.sh
#
#   bash scripts/run_product_completion_until_done.sh TASK-050 TASK-051
#
#   V06_DRY_RUN=1 bash scripts/run_product_completion_until_done.sh
#
# Overnight behavior:
#   - Existing dirty worktree changes are stashed before the queue when
#     V06_AUTOSTASH=1.
#   - Each task still gets the normal run_unattended repair loop.
#   - If a task exhausts repairs, V06_CONTINUE_ON_FAILURE=1 records it as failed,
#     preserves the failed branch or stash, and moves on to the next task.

set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

if [[ -d /opt/homebrew/bin ]]; then
  export PATH="/opt/homebrew/bin:/opt/homebrew/sbin:$PATH"
fi

if [[ -d "$ROOT/.venv/bin" ]]; then
  export PATH="$ROOT/.venv/bin:$PATH"
fi

DEFAULT_TASKS=(TASK-050 TASK-051 TASK-052 TASK-053 TASK-054 TASK-055 TASK-056 TASK-057)
TASKS=("$@")
if [[ "${#TASKS[@]}" -eq 0 ]]; then
  TASKS=("${DEFAULT_TASKS[@]}")
fi

STATE_FILE="${V06_STATE_FILE:-$ROOT/.codex/runs/product_completion_v06_state.tsv}"
MAIN_BRANCH="${MAIN_BRANCH:-v06-product-completion-main}"
REMOTE_MAIN_BRANCH="${REMOTE_MAIN_BRANCH:-main}"
PUSH_BRANCH="${PUSH_BRANCH:-main}"
UNATTENDED_MODE="${UNATTENDED_MODE:-branch}"
AUTO_PUSH="${AUTO_PUSH:-1}"
CODEX_PROVIDER_MODE="${CODEX_PROVIDER_MODE:-chatgpt}"
MAX_REPAIR_ATTEMPTS="${MAX_REPAIR_ATTEMPTS:-3}"
V06_DRY_RUN="${V06_DRY_RUN:-0}"
V06_AUTOSTASH="${V06_AUTOSTASH:-1}"
V06_CONTINUE_ON_FAILURE="${V06_CONTINUE_ON_FAILURE:-1}"
FAILED_TASKS=()

mkdir -p "$(dirname "$STATE_FILE")"
touch "$STATE_FILE"

task_done() {
  local task_id="$1"
  grep -qE "^${task_id}[[:space:]]+DONE[[:space:]]" "$STATE_FILE"
}

record_task_state() {
  local task_id="$1"
  local state="$2"
  local details="$3"
  local tmp_file

  tmp_file="$(mktemp "${TMPDIR:-/tmp}/macroagent-v06-state.XXXXXX")"
  grep -vE "^${task_id}[[:space:]]" "$STATE_FILE" > "$tmp_file" || true
  printf '%s\t%s\t%s\t%s\n' "$task_id" "$state" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$details" \
    >> "$tmp_file"
  mv "$tmp_file" "$STATE_FILE"
}

ensure_briefs_exist() {
  local missing=0
  local task_id

  for task_id in "${TASKS[@]}"; do
    if [[ ! -f "dev_agents/briefs/${task_id}.md" ]]; then
      echo "Missing brief: dev_agents/briefs/${task_id}.md" >&2
      missing=1
    fi
  done

  if [[ "$missing" != "0" ]]; then
    echo "Cannot start until every selected task has an individual brief." >&2
    exit 1
  fi
}

ensure_codex_cli_exists() {
  if ! command -v codex >/dev/null 2>&1; then
    echo "Missing codex CLI on PATH. Install or repair Codex CLI before running this queue." >&2
    exit 1
  fi
  if ! codex --version >/dev/null 2>&1; then
    echo "Codex CLI is installed but not runnable. Repair it before running this queue." >&2
    echo "Common repair: npm install -g @openai/codex@latest" >&2
    exit 1
  fi
}

stash_dirty_worktree_before_run() {
  local stamp
  local stash_ref

  if [[ -z "$(git status --porcelain)" ]]; then
    return
  fi

  if [[ "$V06_AUTOSTASH" != "1" ]]; then
    echo "Worktree is dirty and V06_AUTOSTASH is not enabled; refusing to start." >&2
    git status --short >&2
    exit 1
  fi

  stamp="macroagent-v06-pre-run-$(date -u +%Y%m%dT%H%M%SZ)"
  git stash push -u -m "$stamp"
  stash_ref="$(git stash list --format='%gd %s' | awk -v stamp="$stamp" '$0 ~ stamp {print $1; exit}')"
  echo "Saved pre-run dirty worktree in ${stash_ref:-git stash} ($stamp)."
  record_task_state "__pre_run_stash" "SAVED" "${stash_ref:-unknown}:${stamp}"
}

recover_after_task_failure() {
  local task_id="$1"
  local status="$2"
  local branch
  local details
  local stamp
  local stash_ref

  branch="$(git branch --show-current 2>/dev/null || true)"
  details="exit=${status};branch=${branch:-unknown}"

  if [[ -n "$(git status --porcelain)" ]]; then
    stamp="macroagent-v06-failed-${task_id}-$(date -u +%Y%m%dT%H%M%SZ)"
    git stash push -u -m "$stamp" || true
    stash_ref="$(git stash list --format='%gd %s' | awk -v stamp="$stamp" '$0 ~ stamp {print $1; exit}')"
    details="${details};stash=${stash_ref:-unknown}:${stamp}"
    echo "Saved dirty failure state for $task_id in ${stash_ref:-git stash} ($stamp)."
  fi

  if git show-ref --verify --quiet "refs/heads/$MAIN_BRANCH"; then
    git switch "$MAIN_BRANCH" >/dev/null 2>&1 || true
  fi

  record_task_state "$task_id" "FAILED" "$details"
}

ensure_briefs_exist
if [[ "$V06_DRY_RUN" != "1" ]]; then
  ensure_codex_cli_exists
  stash_dirty_worktree_before_run
fi

echo "MacroAgent v0.6 product completion queue"
echo "Tasks: ${TASKS[*]}"
echo "State: $STATE_FILE"
echo "Local integration branch: $MAIN_BRANCH"
echo "Remote base branch: $REMOTE_MAIN_BRANCH"
echo "Remote push branch: $PUSH_BRANCH"
echo "Mode: $UNATTENDED_MODE"
echo "Dry run: $V06_DRY_RUN"
echo "Auto stash dirty worktree: $V06_AUTOSTASH"
echo "Continue after exhausted task repairs: $V06_CONTINUE_ON_FAILURE"

for task_id in "${TASKS[@]}"; do
  if [[ "${RERUN_COMPLETED:-0}" != "1" ]] && task_done "$task_id"; then
    echo "Skipping already completed task: $task_id"
    continue
  fi

  echo "Starting $task_id"
  if [[ "$V06_DRY_RUN" == "1" ]]; then
    echo "Dry run would execute: bash .codex/scripts/run_unattended.sh $task_id"
    continue
  fi

  set +e
  MAIN_BRANCH="$MAIN_BRANCH" \
    REMOTE_MAIN_BRANCH="$REMOTE_MAIN_BRANCH" \
    PUSH_BRANCH="$PUSH_BRANCH" \
    UNATTENDED_MODE="$UNATTENDED_MODE" \
    AUTO_PUSH="$AUTO_PUSH" \
    CODEX_PROVIDER_MODE="$CODEX_PROVIDER_MODE" \
    MAX_REPAIR_ATTEMPTS="$MAX_REPAIR_ATTEMPTS" \
    bash .codex/scripts/run_unattended.sh "$task_id"
  status="$?"
  set -e

  if [[ "$status" -eq 0 ]]; then
    record_task_state "$task_id" "DONE" "ok"
    echo "Completed $task_id"
  else
    FAILED_TASKS+=("$task_id")
    recover_after_task_failure "$task_id" "$status"
    echo "Task $task_id failed with exit code $status after its repair loop." >&2

    if [[ "$V06_CONTINUE_ON_FAILURE" == "1" ]]; then
      echo "Continuing to the next task because V06_CONTINUE_ON_FAILURE=1." >&2
      continue
    fi

    echo "Stopped at $task_id. Rerun this script after repair." >&2
    exit "$status"
  fi
done

if [[ "${#FAILED_TASKS[@]}" -gt 0 ]]; then
  echo "MacroAgent v0.6 product completion queue finished with failed tasks: ${FAILED_TASKS[*]}" >&2
  echo "Rerun the same command to retry failed tasks; DONE tasks are skipped." >&2
  exit 1
fi

echo "MacroAgent v0.6 product completion queue complete."
