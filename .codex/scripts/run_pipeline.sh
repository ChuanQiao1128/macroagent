#!/usr/bin/env bash
# MacroAgent dev pipeline.
# Usage: bash .codex/scripts/run_pipeline.sh TASK-001

set -euo pipefail

TASK_ID="${1:-}"
if [[ -z "$TASK_ID" ]]; then
  echo "Usage: bash .codex/scripts/run_pipeline.sh TASK-001" >&2
  exit 2
fi

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

if [[ -d "$ROOT/.venv/bin" ]]; then
  export PATH="$ROOT/.venv/bin:$PATH"
fi

BRIEF="dev_agents/briefs/${TASK_ID}.md"
BASE_REF="${BASE_REF:-main}"
CODEX_PROVIDER_MODE="${CODEX_PROVIDER_MODE:-chatgpt}"
REVIEWER_MODEL="${REVIEWER_MODEL:-gpt-5.5}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
PIPELINE_CHECKPOINT_COMMITS="${PIPELINE_CHECKPOINT_COMMITS:-0}"

if [[ ! -f "$BRIEF" ]]; then
  echo "Brief not found: $BRIEF" >&2
  exit 1
fi

if ! git rev-parse --verify "$BASE_REF" >/dev/null 2>&1; then
  echo "Base ref not found: $BASE_REF" >&2
  echo "Set BASE_REF=origin/main after adding the GitHub remote." >&2
  exit 1
fi

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "Python interpreter not found: $PYTHON_BIN" >&2
  exit 1
fi

if [[ "$PIPELINE_CHECKPOINT_COMMITS" == "1" && -n "$(git status --porcelain)" ]]; then
  echo "PIPELINE_CHECKPOINT_COMMITS=1 requires a clean worktree at pipeline start" >&2
  git status --short >&2
  exit 1
fi

checkpoint_role() {
  local role="$1"

  if [[ "$PIPELINE_CHECKPOINT_COMMITS" != "1" ]]; then
    return
  fi

  if [[ -z "$(git status --porcelain)" ]]; then
    echo "No ${role} changes to checkpoint"
    return
  fi

  git add -A
  git commit -m "agent(${TASK_ID}): ${role}"
}

check_role_acl() {
  local role="$1"
  local base="$2"

  "$PYTHON_BIN" dev_agents/policies/check_acl.py \
    --role "$role" \
    --base "$base" \
    --head WORKTREE
}

run_role() {
  local role="$1"
  local model="$2"
  local sandbox="$3"
  local output_file="${4:-}"
  local role_file=".codex/roles/${role}.md"
  local provider_mode="$CODEX_PROVIDER_MODE"
  local prompt_file

  if [[ ! -f "$role_file" ]]; then
    echo "Role file not found: $role_file" >&2
    exit 1
  fi

  case "$provider_mode" in
    chatgpt|openai)
      ;;
    helicone)
      if [[ -z "${OPENAI_API_KEY:-}" || -z "${HELICONE_API_KEY:-}" ]]; then
        echo "Helicone mode requires OPENAI_API_KEY and HELICONE_API_KEY" >&2
        exit 1
      fi
      export HELICONE_AUTH_HEADER="Bearer ${HELICONE_API_KEY}"
      ;;
    *)
      echo "Unsupported CODEX_PROVIDER_MODE: $provider_mode" >&2
      echo "Use chatgpt or helicone." >&2
      exit 1
      ;;
  esac

  prompt_file="$(mktemp "${TMPDIR:-/tmp}/macroagent-${TASK_ID}-${role}.XXXXXX")"
  {
    printf '# Shared project context\n\n'
    cat .codex/AGENTS.md
    printf '\n\n# Role instructions: %s\n\n' "$role"
    cat "$role_file"
    printf '\n\n# Agent brief: %s\n\n' "$TASK_ID"
    cat "$BRIEF"
  } > "$prompt_file"

  if [[ "$provider_mode" == "helicone" ]]; then
    if [[ -n "$output_file" ]]; then
      codex exec \
        --model "$model" \
        --config 'model_provider="helicone"' \
        --sandbox "$sandbox" \
        --cd "$ROOT" \
        --output-last-message "$output_file" \
        - < "$prompt_file"
    else
      codex exec \
        --model "$model" \
        --config 'model_provider="helicone"' \
        --sandbox "$sandbox" \
        --cd "$ROOT" \
        - < "$prompt_file"
    fi
  else
    if [[ -n "$output_file" ]]; then
      codex exec \
        --model "$model" \
        --sandbox "$sandbox" \
        --cd "$ROOT" \
        --output-last-message "$output_file" \
        - < "$prompt_file"
    else
      codex exec \
        --model "$model" \
        --sandbox "$sandbox" \
        --cd "$ROOT" \
        - < "$prompt_file"
    fi
  fi

  rm -f "$prompt_file"
}

echo "Pipeline starting for $TASK_ID"
echo "Provider mode: $CODEX_PROVIDER_MODE"

echo "Step 1: Developer"
DEVELOPER_BASE="$BASE_REF"
if [[ "$PIPELINE_CHECKPOINT_COMMITS" == "1" ]]; then
  DEVELOPER_BASE="$(git rev-parse HEAD)"
fi
run_role "developer" "gpt-5.3-codex" "workspace-write"

echo "Step 2: Developer ACL check"
check_role_acl "developer" "$DEVELOPER_BASE"
checkpoint_role "developer"

echo "Step 3: Tester"
TESTER_BASE="$(git rev-parse HEAD)"
run_role "tester" "gpt-5.3-codex" "workspace-write"
if [[ "$PIPELINE_CHECKPOINT_COMMITS" == "1" ]]; then
  echo "Step 3b: Tester ACL check"
  check_role_acl "tester" "$TESTER_BASE"
  checkpoint_role "tester"
fi

echo "Step 4: Tests and evals"
RETRY=false
if [[ -d tests ]]; then
  if command -v pytest >/dev/null 2>&1; then
    pytest tests/ || RETRY=true
  else
    echo "pytest is not installed or not on PATH" >&2
    RETRY=true
  fi
else
  echo "No tests/ directory exists after Tester step" >&2
  RETRY=true
fi

if [[ -f evals/run_eval.py ]]; then
  "$PYTHON_BIN" evals/run_eval.py --fail-on-regression || RETRY=true
else
  echo "No evals/run_eval.py found; skipping eval gate"
fi

ATTEMPTS=0
while [[ "$RETRY" == "true" && "$ATTEMPTS" -lt 3 ]]; do
  echo "Step 5: Bug Fixer attempt $((ATTEMPTS + 1))/3"
  BUG_FIXER_BASE="$BASE_REF"
  if [[ "$PIPELINE_CHECKPOINT_COMMITS" == "1" ]]; then
    BUG_FIXER_BASE="$(git rev-parse HEAD)"
  fi
  run_role "bug_fixer" "gpt-5.3-codex" "workspace-write"
  check_role_acl "bug_fixer" "$BUG_FIXER_BASE"
  checkpoint_role "bug_fixer"

  RETRY=false
  if [[ -d tests ]]; then
    if command -v pytest >/dev/null 2>&1; then
      pytest tests/ || RETRY=true
    else
      echo "pytest is not installed or not on PATH" >&2
      RETRY=true
    fi
  else
    RETRY=true
  fi
  if [[ -f evals/run_eval.py ]]; then
    "$PYTHON_BIN" evals/run_eval.py --fail-on-regression || RETRY=true
  fi
  ATTEMPTS=$((ATTEMPTS + 1))
done

if [[ "$RETRY" == "true" ]]; then
  echo "Bug Fixer exhausted 3 retries for $TASK_ID" >&2
  exit 1
fi

echo "Step 6: Reviewer"
REVIEW_LAST_MESSAGE="$(mktemp "${TMPDIR:-/tmp}/macroagent-review-${TASK_ID}.XXXXXX")"
run_role "reviewer" "$REVIEWER_MODEL" "read-only" "$REVIEW_LAST_MESSAGE"
if grep -Eiq '(^|[^[:alpha:]_])REQUEST_CHANGES([^[:alpha:]_]|$)' "$REVIEW_LAST_MESSAGE"; then
  echo "Reviewer requested changes for $TASK_ID" >&2
  cat "$REVIEW_LAST_MESSAGE" >&2
  exit 1
fi

echo "Step 7: Doc"
DOC_BASE="$(git rev-parse HEAD)"
run_role "doc" "gpt-5.4-mini" "workspace-write"
if [[ "$PIPELINE_CHECKPOINT_COMMITS" == "1" ]]; then
  echo "Step 7b: Doc ACL check"
  check_role_acl "doc" "$DOC_BASE"
  checkpoint_role "doc"
fi

echo "Pipeline complete for $TASK_ID"
