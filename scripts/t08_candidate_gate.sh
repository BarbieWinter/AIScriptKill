#!/usr/bin/env bash

set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
API_BASE_URL="http://127.0.0.1:8000"
WEB_BASE_URL="http://127.0.0.1:3000"
CANDIDATE_BASE_REF="${T08_CANDIDATE_BASE_REF:-main}"
ADMIN_EMAIL="t08-candidate-admin@local.invalid"
ADMIN_PASSWORD="t08-candidate-local-password"
WORK_DIR="$(mktemp -d "${TMPDIR:-/tmp}/aiscriptkill-t08.XXXXXX")"
API_LOG="$WORK_DIR/api.log"
WEB_LOG="$WORK_DIR/web.log"
API_PID=""
WEB_PID=""

log() {
  printf '\n[T08] %s\n' "$1"
}

fail() {
  printf '\n[T08] FAILED: %s\n' "$1" >&2
  exit 1
}

cleanup() {
  local exit_code=$?

  if [[ -n "$WEB_PID" ]]; then
    kill "$WEB_PID" 2>/dev/null || true
    wait "$WEB_PID" 2>/dev/null || true
  fi
  if [[ -n "$API_PID" ]]; then
    kill "$API_PID" 2>/dev/null || true
    wait "$API_PID" 2>/dev/null || true
  fi

  if [[ $exit_code -ne 0 ]]; then
    if [[ -s "$API_LOG" ]]; then
      printf '\n[T08] FastAPI log:\n' >&2
      tail -n 80 "$API_LOG" >&2
    fi
    if [[ -s "$WEB_LOG" ]]; then
      printf '\n[T08] Next.js log:\n' >&2
      tail -n 80 "$WEB_LOG" >&2
    fi
    printf '\n[T08] Failure artifacts: %s\n' "$WORK_DIR" >&2
    return
  fi

  rm -rf "$WORK_DIR"
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || fail "required command is missing: $1"
}

require_service_stopped() {
  local url=$1
  local description=$2

  if curl --silent --output /dev/null --max-time 1 "$url"; then
    fail "$description is already reachable; stop it before running the gate"
  fi
}

wait_for_service() {
  local url=$1
  local description=$2
  local pid=$3

  for _ in {1..120}; do
    kill -0 "$pid" 2>/dev/null || fail "$description exited before becoming ready"
    if curl --fail --silent "$url" >/dev/null; then
      return
    fi
    sleep 1
  done
  fail "$description did not become ready: $url"
}

load_supabase_environment() {
  eval "$(supabase status -o env)"
  export SUPABASE_URL="$API_URL"
  export SUPABASE_PUBLISHABLE_KEY="$PUBLISHABLE_KEY"
  export SUPABASE_SECRET_KEY="$SECRET_KEY"
  export DATABASE_URL="$DB_URL"
  export DATABASE_POOLER_URL=""
  export NEXT_PUBLIC_SUPABASE_URL="$API_URL"
  export NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY="$PUBLISHABLE_KEY"
  export NEXT_PUBLIC_USE_MOCK=false
  export MULTIPLAYER_V1=true
  export RAG_EMBEDDING_PROVIDER=deterministic
  export AISCRIPTKILL_MULTIPLAYER_COMMAND_DB_URL="$DB_URL"
  export AISCRIPTKILL_MP3_RECOVERY_DB_URL="$DB_URL"
  export AISCRIPTKILL_PROCESS_RECOVERY_DB_URL="$DB_URL"
  export AISCRIPTKILL_DATABASE_PRIVILEGE_DB_URL="$DB_URL"
}

reset_blank_database() {
  supabase db reset --local --no-seed --yes
  load_supabase_environment
}

create_admin_access_token() {
  local create_payload
  local token_response

  create_payload="$(jq -n \
    --arg email "$ADMIN_EMAIL" \
    --arg password "$ADMIN_PASSWORD" \
    '{email: $email, password: $password, email_confirm: true, app_metadata: {role: "admin"}}')"
  curl --fail-with-body --silent --show-error \
    --request POST "$SUPABASE_URL/auth/v1/admin/users" \
    --header "apikey: $SUPABASE_SECRET_KEY" \
    --header "Authorization: Bearer $SUPABASE_SECRET_KEY" \
    --header "Content-Type: application/json" \
    --data "$create_payload" >/dev/null

  token_response="$(curl --fail-with-body --silent --show-error \
    --request POST "$SUPABASE_URL/auth/v1/token?grant_type=password" \
    --header "apikey: $SUPABASE_PUBLISHABLE_KEY" \
    --header "Content-Type: application/json" \
    --data "$(jq -n --arg email "$ADMIN_EMAIL" --arg password "$ADMIN_PASSWORD" \
      '{email: $email, password: $password}')")"
  jq -er '.access_token' <<<"$token_response"
}

zip_output_path() {
  if command -v cygpath >/dev/null 2>&1; then
    cygpath -w "$1"
  else
    printf '%s\n' "$1"
  fi
}

publish_canonical_package() {
  local archive="$WORK_DIR/mp1-two-player.zip"
  local response_file="$WORK_DIR/package-import.json"
  local http_status
  local response

  (
    cd "$ROOT_DIR/script-packages"
    zip -qr -D "$(zip_output_path "$archive")" mp1-two-player
  )
  http_status="$(curl --silent --show-error \
    --output "$response_file" \
    --write-out '%{http_code}' \
    --request POST "$API_BASE_URL/api/v1/packages?publish=true" \
    --header "Authorization: Bearer $1" \
    --form "file=@$archive;type=application/zip")"
  response="$(<"$response_file")"
  [[ "$http_status" == 2* ]] || fail "canonical package publication failed with HTTP $http_status: $response"
  jq -e '.package_id == "mp1-two-player" and .status == "published" and .validation.valid == true' \
    <<<"$response" >/dev/null || fail "canonical package publication returned an unexpected response: $response"
}

trap cleanup EXIT
trap 'exit 130' INT TERM
cd "$ROOT_DIR"

require_command git
T08_CANDIDATE_BASE_REF="$CANDIDATE_BASE_REF" \
  "$ROOT_DIR/scripts/t08_candidate_tree_check.sh"

for command_name in curl jq npm supabase uv zip; do
  require_command "$command_name"
done
require_service_stopped "$API_BASE_URL/health/db" "FastAPI"
require_service_stopped "$WEB_BASE_URL/multiplayer" "Next.js"

log "Provisioning a blank migrated Supabase database"
supabase status >/dev/null 2>&1 || supabase start -x vector,logflare
reset_blank_database

log "Running static analysis"
make lint
make typecheck-api

log "Running the complete backend and database suite"
uv run --frozen pytest engine/tests/ -q

log "Running route-mocked browser journeys"
CI=1 npm --prefix apps/web run test:e2e

log "Building the production frontend"
npm --prefix apps/web run build

# Database-backed tests are allowed to create disposable rows. Reset again so the
# live journey proves publication and play from a genuinely blank runtime store.
log "Resetting the live candidate database"
reset_blank_database

log "Starting FastAPI and the production Next.js server"
uv run uvicorn engine.api.main:app --host 127.0.0.1 --port 8000 >"$API_LOG" 2>&1 &
API_PID=$!
npm --prefix apps/web run start -- --hostname 127.0.0.1 --port 3000 >"$WEB_LOG" 2>&1 &
WEB_PID=$!
wait_for_service "$API_BASE_URL/health/db" "FastAPI/database" "$API_PID"
wait_for_service "$WEB_BASE_URL/multiplayer" "Next.js" "$WEB_PID"

log "Publishing the canonical package through the administration API"
ADMIN_ACCESS_TOKEN="$(create_admin_access_token)"
publish_canonical_package "$ADMIN_ACCESS_TOKEN"

log "Running the real two-identity candidate journey"
PLAYWRIGHT_API_BASE_URL="$API_BASE_URL" \
PLAYWRIGHT_BASE_URL="$WEB_BASE_URL" \
npm --prefix apps/web run test:e2e:mp2-live

log "Candidate gate passed"
