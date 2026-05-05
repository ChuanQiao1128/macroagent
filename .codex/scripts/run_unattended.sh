#!/usr/bin/env bash
# Run one or more agent briefs without waiting for human review.
#
# Default mode is intentionally branch-based: each task runs on a fresh branch,
# passes local checks, then fast-forwards main and pushes. Set
# UNATTENDED_MODE=direct to run and commit directly on main.
#
# Usage:
#   bash .codex/scripts/run_unattended.sh TASK-002 [TASK-003 ...]

set -euo pipefail

if [[ "$#" -lt 1 ]]; then
  echo "Usage: bash .codex/scripts/run_unattended.sh TASK-002 [TASK-003 ...]" >&2
  exit 2
fi

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

if [[ -d "$ROOT/.venv/bin" ]]; then
  export PATH="$ROOT/.venv/bin:$PATH"
fi

MAIN_BRANCH="${MAIN_BRANCH:-main}"
REMOTE_MAIN_BRANCH="${REMOTE_MAIN_BRANCH:-$MAIN_BRANCH}"
PUSH_BRANCH="${PUSH_BRANCH:-$MAIN_BRANCH}"
UNATTENDED_MODE="${UNATTENDED_MODE:-branch}"
AUTO_PUSH="${AUTO_PUSH:-1}"
DELETE_TASK_BRANCH="${DELETE_TASK_BRANCH:-0}"
CODEX_PROVIDER_MODE="${CODEX_PROVIDER_MODE:-chatgpt}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
MAX_REPAIR_ATTEMPTS="${MAX_REPAIR_ATTEMPTS:-3}"
REPAIR_MODEL="${REPAIR_MODEL:-gpt-5.3-codex}"
REPAIR_LOG_LINES="${REPAIR_LOG_LINES:-240}"
RUN_LOG_DIR="${RUN_LOG_DIR:-$ROOT/.codex/runs}"
REMOTE_URL="${UNATTENDED_REMOTE_URL:-$(git remote get-url origin 2>/dev/null || true)}"

if [[ "$REMOTE_URL" =~ ^git@github.com:(.+)\.git$ ]]; then
  REMOTE_URL="https://github.com/${BASH_REMATCH[1]}.git"
fi

if [[ "$AUTO_PUSH" == "1" && -z "$REMOTE_URL" ]]; then
  echo "AUTO_PUSH=1 requires origin or UNATTENDED_REMOTE_URL" >&2
  exit 1
fi

mkdir -p "$RUN_LOG_DIR"

ensure_clean() {
  if [[ -n "$(git status --porcelain)" ]]; then
    echo "Worktree is not clean; refusing to start unattended mode." >&2
    git status --short >&2
    exit 1
  fi
}

sync_main() {
  if [[ -n "$REMOTE_URL" ]]; then
    git fetch "$REMOTE_URL" "$REMOTE_MAIN_BRANCH"
    if git show-ref --verify --quiet "refs/heads/$MAIN_BRANCH"; then
      git switch "$MAIN_BRANCH"
      git merge --ff-only FETCH_HEAD
    else
      git switch -c "$MAIN_BRANCH" FETCH_HEAD
    fi
  else
    git switch "$MAIN_BRANCH"
  fi
}

safe_task_name() {
  printf "%s" "$1" | tr "[:upper:]" "[:lower:]" | tr -c "[:alnum:]._-" "-"
}

changed_files_since() {
  local base="$1"
  {
    git diff --name-only "$base"..HEAD
    git diff --name-only
    git diff --cached --name-only
    git ls-files --others --exclude-standard
  } | sort -u
}

assert_no_protected_changes() {
  local base="$1"
  local blocked=0
  local path

  while IFS= read -r path; do
    case "$path" in
      DESIGN_zh*.md|prompts/*|evals/golden_set/*|.codex/*|.github/*|dev_agents/policies/*|docs/adr/*)
        echo "Protected path changed in unattended task: $path" >&2
        blocked=1
        ;;
    esac
  done < <(changed_files_since "$base")

  if [[ "$blocked" != "0" ]]; then
    echo "Stopping before commit/merge. Handle protected-path changes manually." >&2
    exit 1
  fi
}

restore_generated_protected_changes() {
  local base="$1"
  local restored=0
  local path

  while IFS= read -r path; do
    case "$path" in
      DESIGN_zh*.md|prompts/*|evals/golden_set/*|.codex/*|.github/*|dev_agents/policies/*|docs/adr/*)
        if git cat-file -e "${base}:${path}" 2>/dev/null; then
          git restore --source "$base" --staged --worktree -- "$path"
        else
          git rm -f --ignore-unmatch -- "$path" >/dev/null 2>&1 || true
          rm -rf -- "$path"
        fi
        echo "Restored protected generated change: $path"
        restored=1
        ;;
    esac
  done < <(changed_files_since "$base")

  return "$restored"
}

run_repair() {
  local task_id="$1"
  local base="$2"
  local failure_log="$3"
  local attempt="$4"
  local safe_task
  local repair_log
  local prompt_file

  safe_task="$(safe_task_name "$task_id")"
  repair_log="$RUN_LOG_DIR/$(date -u +%Y%m%dT%H%M%SZ)-${safe_task}-repair-${attempt}.log"

  restore_generated_protected_changes "$base" || true

  prompt_file="$(mktemp "${TMPDIR:-/tmp}/macroagent-${task_id}-repair-${attempt}.XXXXXX")"
  {
    printf '# Shared project context\n\n'
    cat .codex/AGENTS.md
    printf '\n\n# Role instructions: bug_fixer\n\n'
    cat .codex/roles/bug_fixer.md
    printf '\n\n# Agent brief: %s\n\n' "$task_id"
    cat "dev_agents/briefs/${task_id}.md"
    printf '\n\n# Unattended repair instructions\n\n'
    printf 'The unattended pipeline failed. Repair the current branch so the same pipeline can pass on the next attempt.\n'
    printf 'Use the failure log below as the source of truth. Keep changes minimal and within the bug_fixer ACL.\n'
    printf 'Do not edit DESIGN_zh*.md, prompts/**, evals/golden_set/**, .codex/**, .github/**, dev_agents/policies/**, or docs/adr/**.\n'
    printf 'If a forbidden file was accidentally changed, restore it to the base behavior/content instead of extending it.\n'
    printf 'After editing, run focused tests or lint that are relevant to your fix.\n'
    printf '\n\n# Failure log tail\n\n'
    tail -n "$REPAIR_LOG_LINES" "$failure_log"
  } > "$prompt_file"

  case "$CODEX_PROVIDER_MODE" in
    chatgpt|openai)
      codex exec \
        --model "$REPAIR_MODEL" \
        --sandbox workspace-write \
        --cd "$ROOT" \
        - < "$prompt_file" 2>&1 | tee "$repair_log"
      ;;
    helicone)
      if [[ -z "${OPENAI_API_KEY:-}" || -z "${HELICONE_API_KEY:-}" ]]; then
        echo "Helicone mode requires OPENAI_API_KEY and HELICONE_API_KEY" >&2
        return 1
      fi
      export HELICONE_AUTH_HEADER="Bearer ${HELICONE_API_KEY}"
      codex exec \
        --model "$REPAIR_MODEL" \
        --config 'model_provider="helicone"' \
        --sandbox workspace-write \
        --cd "$ROOT" \
        - < "$prompt_file" 2>&1 | tee "$repair_log"
      ;;
    *)
      echo "Unsupported CODEX_PROVIDER_MODE: $CODEX_PROVIDER_MODE" >&2
      return 1
      ;;
  esac

  rm -f "$prompt_file"

  restore_generated_protected_changes "$base" || true

  if [[ -n "$(git status --porcelain)" ]]; then
    "$PYTHON_BIN" dev_agents/policies/check_acl.py \
      --role bug_fixer \
      --base "$base" \
      --head WORKTREE
    git add -A
    git commit -m "agent(${task_id}): repair attempt ${attempt}"
  else
    echo "Repair attempt ${attempt} produced no changes."
  fi
}

run_pipeline_with_repairs() {
  local task_id="$1"
  local attempt=0
  local safe_task
  local timestamp
  local log_file
  local pipeline_status

  safe_task="$(safe_task_name "$task_id")"

  while true; do
    timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
    log_file="$RUN_LOG_DIR/${timestamp}-${safe_task}-pipeline-attempt-${attempt}.log"

    set +e
    PIPELINE_CHECKPOINT_COMMITS=1 \
      BASE_REF="$(git rev-parse HEAD)" \
      CODEX_PROVIDER_MODE="$CODEX_PROVIDER_MODE" \
      PYTHON_BIN="$PYTHON_BIN" \
      bash .codex/scripts/run_pipeline.sh "$task_id" 2>&1 | tee "$log_file"
    pipeline_status="${PIPESTATUS[0]}"
    set -e

    if [[ "$pipeline_status" -eq 0 ]]; then
      return 0
    fi

    if [[ "$attempt" -ge "$MAX_REPAIR_ATTEMPTS" ]]; then
      echo "Pipeline failed for $task_id after ${MAX_REPAIR_ATTEMPTS} repair attempt(s)." >&2
      echo "Last log: $log_file" >&2
      return "$pipeline_status"
    fi

    attempt=$((attempt + 1))
    echo "Pipeline failed for $task_id; starting repair attempt ${attempt}/${MAX_REPAIR_ATTEMPTS}."
    run_repair "$task_id" "$(git rev-parse HEAD)" "$log_file" "$attempt"
  done
}

run_final_checks() {
  local lint_targets=()

  if [[ -d tests ]]; then
    pytest tests/
  fi

  for target in services tests dev_agents; do
    if [[ -d "$target" ]]; then
      lint_targets+=("$target")
    fi
  done

  if [[ "${#lint_targets[@]}" -gt 0 ]]; then
    ruff check "${lint_targets[@]}"
  fi

  bash -n .codex/scripts/run_pipeline.sh
}

commit_if_needed() {
  local base="$1"
  local task_id="$2"

  if [[ -z "$(changed_files_since "$base")" ]]; then
    echo "No changes produced for $task_id"
    return 1
  fi

  if [[ -n "$(git status --porcelain)" ]]; then
    git add -A
    git commit -m "agent: complete $task_id"
  else
    echo "Changes for $task_id are already checkpointed."
  fi
}

push_main() {
  if [[ "$AUTO_PUSH" != "1" ]]; then
    echo "AUTO_PUSH=0; main was not pushed."
    return
  fi

  git push "$REMOTE_URL" "$MAIN_BRANCH:refs/heads/$PUSH_BRANCH"
  git fetch "$REMOTE_URL" "$PUSH_BRANCH:refs/remotes/origin/$PUSH_BRANCH" || true
}

run_task_on_branch() {
  local task_id="$1"
  local safe_task
  local timestamp
  local branch
  local log_file

  safe_task="$(safe_task_name "$task_id")"
  timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
  branch="codex/${safe_task}-${timestamp}"
  log_file="$RUN_LOG_DIR/${timestamp}-${safe_task}.log"

  if [[ ! -f "dev_agents/briefs/${task_id}.md" ]]; then
    echo "Brief not found: dev_agents/briefs/${task_id}.md" >&2
    exit 1
  fi

  sync_main
  git switch -c "$branch" "$MAIN_BRANCH"

  echo "Running $task_id on $branch"
  run_pipeline_with_repairs "$task_id"

  assert_no_protected_changes "$MAIN_BRANCH"
  run_final_checks

  if ! commit_if_needed "$MAIN_BRANCH" "$task_id"; then
    git switch "$MAIN_BRANCH"
    return
  fi

  git switch "$MAIN_BRANCH"
  git merge --ff-only "$branch"
  push_main

  if [[ "$DELETE_TASK_BRANCH" == "1" ]]; then
    git branch -d "$branch"
  fi
}

run_task_direct() {
  local task_id="$1"
  local base_sha
  local timestamp
  local safe_task

  if [[ ! -f "dev_agents/briefs/${task_id}.md" ]]; then
    echo "Brief not found: dev_agents/briefs/${task_id}.md" >&2
    exit 1
  fi

  sync_main
  base_sha="$(git rev-parse HEAD)"
  safe_task="$(safe_task_name "$task_id")"

  echo "Running $task_id directly on $MAIN_BRANCH"
  run_pipeline_with_repairs "$task_id"

  assert_no_protected_changes "$base_sha"
  run_final_checks
  commit_if_needed "$base_sha" "$task_id" || return
  push_main
}

ensure_clean

case "$UNATTENDED_MODE" in
  branch)
    for task_id in "$@"; do
      run_task_on_branch "$task_id"
    done
    ;;
  direct)
    for task_id in "$@"; do
      run_task_direct "$task_id"
    done
    ;;
  *)
    echo "Unsupported UNATTENDED_MODE: $UNATTENDED_MODE" >&2
    echo "Use branch or direct." >&2
    exit 2
    ;;
esac

echo "Unattended run complete."
