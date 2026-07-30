#!/usr/bin/env bash

set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CANDIDATE_BASE_REF="${T08_CANDIDATE_BASE_REF:-main}"

log() {
  printf '\n[T08] %s\n' "$1"
}

fail() {
  printf '\n[T08] FAILED: %s\n' "$1" >&2
  exit 1
}

append_hidden_path() {
  local kind=$1
  local entry=$2
  local path=${entry#? }
  if [[ -n "$HIDDEN_INDEX_PATHS" ]]; then
    HIDDEN_INDEX_PATHS+=$'\n'
  fi
  HIDDEN_INDEX_PATHS+="$kind $path"
}

cd "$ROOT_DIR"
log "Checking candidate repository cleanliness"

git rev-parse --is-inside-work-tree >/dev/null 2>&1 \
  || fail "candidate root is not a git worktree"

HIDDEN_INDEX_PATHS=""
while IFS= read -r entry; do
  case "${entry%% *}" in
    [[:lower:]]) append_hidden_path "assume-unchanged" "$entry" ;;
  esac
done < <(git ls-files -v)
while IFS= read -r entry; do
  case "${entry%% *}" in
    S) append_hidden_path "skip-worktree" "$entry" ;;
  esac
done < <(git ls-files -t)
if [[ -n "$HIDDEN_INDEX_PATHS" ]]; then
  printf '%s\n' "$HIDDEN_INDEX_PATHS" >&2
  fail "candidate worktree must be clean; hidden index flags are not allowed"
fi

dirty_status="$(git status --porcelain=v1 --untracked-files=all)" \
  || fail "cannot inspect candidate worktree"
if [[ -n "$dirty_status" ]]; then
  printf '%s\n' "$dirty_status" >&2
  fail "candidate worktree must be clean"
fi

base_commit="$(git merge-base HEAD "$CANDIDATE_BASE_REF")" \
  || fail "cannot resolve candidate base ref: $CANDIDATE_BASE_REF"
git diff --check "$base_commit"
git diff --cached --check

if conflict_markers="$(git grep --untracked -nE '^(<<<<<<< |=======|>>>>>>> )' -- .)"; then
  printf '%s\n' "$conflict_markers" >&2
  fail "candidate tree contains unresolved conflict markers"
fi

log "Candidate tree check passed"
