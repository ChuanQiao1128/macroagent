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

BRIEF="dev_agents/briefs/${TASK_ID}.md"
BASE_REF="${BASE_REF:-main}"

if [[ -n "${HELICONE_API_KEY:-}" && -z "${HELICONE_AUTH_HEADER:-}" ]]; then
  export HELICONE_AUTH_HEADER="Bearer ${HELICONE_API_KEY}"
fi

if [[ ! -f "$BRIEF" ]]; then
  echo "Brief not found: $BRIEF" >&2
  exit 1
fi

if ! git rev-parse --verify "$BASE_REF" >/dev/null 2>&1; then
  echo "Base ref not found: $BASE_REF" >&2
  echo "Set BASE_REF=origin/main after adding the GitHub remote." >&2
  exit 1
fi

run_role() {
  local role="$1"
  local model="$2"
  local sandbox="$3"
  local role_file=".codex/roles/${role}.md"

  if [[ ! -f "$role_file" ]]; then
    echo "Role file not found: $role_file" >&2
    exit 1
  fi

  {
    printf '# Shared project context\n\n'
    cat .codex/AGENTS.md
    printf '\n\n# Role instructions: %s\n\n' "$role"
    cat "$role_file"
    printf '\n\n# Agent brief: %s\n\n' "$TASK_ID"
    cat "$BRIEF"
  } | codex exec \
    --model "$model" \
    --config 'model_provider="helicone"' \
    --sandbox "$sandbox" \
    --cd "$ROOT" \
    -
}

echo "Pipeline starting for $TASK_ID"

echo "Step 1: Developer"
run_role "developer" "gpt-5.3-codex" "workspace-write"

echo "Step 2: Developer ACL check"
python dev_agents/policies/check_acl.py \
  --role developer \
  --base "$BASE_REF" \
  --head WORKTREE

echo "Step 3: Tester"
run_role "tester" "gpt-5.3-codex" "workspace-write"

echo "Step 4: Tests and evals"
RETRY=false
if [[ -d tests ]]; then
  pytest tests/ || RETRY=true
else
  echo "No tests/ directory exists after Tester step" >&2
  RETRY=true
fi

if [[ -f evals/run_eval.py ]]; then
  python evals/run_eval.py --fail-on-regression || RETRY=true
else
  echo "No evals/run_eval.py found; skipping eval gate"
fi

ATTEMPTS=0
while [[ "$RETRY" == "true" && "$ATTEMPTS" -lt 3 ]]; do
  echo "Step 5: Bug Fixer attempt $((ATTEMPTS + 1))/3"
  run_role "bug_fixer" "gpt-5.3-codex" "workspace-write"
  python dev_agents/policies/check_acl.py \
    --role bug_fixer \
    --base "$BASE_REF" \
    --head WORKTREE

  RETRY=false
  if [[ -d tests ]]; then
    pytest tests/ || RETRY=true
  else
    RETRY=true
  fi
  if [[ -f evals/run_eval.py ]]; then
    python evals/run_eval.py --fail-on-regression || RETRY=true
  fi
  ATTEMPTS=$((ATTEMPTS + 1))
done

if [[ "$RETRY" == "true" ]]; then
  echo "Bug Fixer exhausted 3 retries for $TASK_ID" >&2
  exit 1
fi

echo "Step 6: Reviewer"
run_role "reviewer" "o3" "read-only"

echo "Step 7: Doc"
run_role "doc" "gpt-5.4-mini" "workspace-write"

echo "Pipeline complete for $TASK_ID"
