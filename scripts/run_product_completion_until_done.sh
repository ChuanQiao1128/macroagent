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

ensure_briefs_exist
if [[ "$V06_DRY_RUN" != "1" ]]; then
  ensure_codex_cli_exists
fi

echo "MacroAgent v0.6 product completion queue"
echo "Tasks: ${TASKS[*]}"
echo "State: $STATE_FILE"
echo "Local integration branch: $MAIN_BRANCH"
echo "Remote base branch: $REMOTE_MAIN_BRANCH"
echo "Remote push branch: $PUSH_BRANCH"
echo "Mode: $UNATTENDED_MODE"
echo "Dry run: $V06_DRY_RUN"

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
    record_task_state "$task_id" "FAILED" "exit=${status}"
    echo "Stopped at $task_id with exit code $status" >&2
    echo "Inspect recent logs in .codex/runs/ and rerun this script after repair." >&2
    exit "$status"
  fi
done

echo "MacroAgent v0.6 product completion queue complete."
