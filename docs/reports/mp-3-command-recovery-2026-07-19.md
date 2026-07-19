# MP-3 Legacy Command Recovery Report

Date: 2026-07-19

## Scope

This increment connects durable HTTP recovery to `POST /sessions/{session_id}/actions` only when a `legacy_single` request supplies the paired `command_id` and `expected_revision` fields.

It does **not** make the MP-2 `POST /sessions/{session_id}/commands` room protocol into durable multiplayer gameplay. It also does not add multiplayer participant gameplay snapshots, durable multiplayer chat/settlement, or authenticated WebSocket replay.

## Implemented

### Receipt authority and attempt fencing

- A processing receipt owns a database-time lease and a positive, monotonically increasing `attempt_count`.
- An expired lease is reclaimed with one compare-and-swap update over `(session_id, command_id, status, attempt_count, lease_expires_at)`.
- Receipt reject, fail, lease renewal, and success finalization are fenced by the owning attempt.
- A partial unique index permits at most one processing receipt per session.
- The forward migration aborts before creating that index if duplicate processing receipts require operator reconciliation; it never chooses a winner by timestamp.
- An old attempt cannot publish a public event after losing receipt authority.

### Checkpoint lineage and continuation

- Durable command checkpoints and pending writes carry `command_id` and `command_attempt`.
- Every tagged write verifies the corresponding processing receipt generation and renews its lease using database time.
- Recovery searches command checkpoints through the current attempt instead of using an unrelated thread-latest checkpoint.
- A command with no durable checkpoint executes once from the claim-time canonical private base state.
- A partial checkpoint resumes with `graph.ainvoke(None, exact_config)` and does not re-submit the player input.
- A quiescent checkpoint is settled directly without another graph invocation.
- The stored base-state SHA-256 is verified before recovery; corrupt or incomplete private state fails closed.

### Atomic public finalization

- Runtime execution returns the authoritative final checkpoint ID and final `GameState` to the coordinator.
- The coordinator hashes canonical sorted compact JSON for the complete final state and writes the digest to both the receipt and public event row.
- The public event payload contains only the safe action result projection. It does not contain the private game state, answer key, package, or checkpoint contents.
- Session revision/event-head compare-and-swap, public event insertion, and terminal receipt update remain in one request transaction.
- If a durable command checkpoint exists when execution raises unexpectedly, the receipt remains recoverable processing with an expired lease rather than being incorrectly terminalized as failed.

### Browser recovery

- Each user intent creates one immutable UUID/envelope before the first POST and captures the latest authoritative revision.
- Ambiguous transport results query the same receipt; `COMMAND_NOT_FOUND` permits one exact-envelope replay.
- Processing checks are bounded and expose a same-UUID manual recovery action.
- Revision conflicts clear the stale intent and resynchronize without replaying it.
- Replay validation rejects event gaps and regressing coordinates before rebuilding the browser projection through REST resources.

## Automated evidence

Executed in the isolated target checkout:

- Focused MP-3 recovery/checkpoint/coordinator tests: `31 passed`.
- Expanded focused lane including PostgreSQL-gated recovery tests: `28 passed, 2 skipped`.
- Full backend test suite: `480 passed, 4 skipped`.
- Production backend BasedPyright target: `0 errors, 0 warnings, 0 notes`.
- Ruff checks passed for the changed recovery files.
- Web ESLint and the corrected project TypeScript check passed in the same validation cycle.

The focused tests cover reclaim CAS, stale terminal/event fencing, checkpoint attempt tagging, cross-attempt lookup, hash-verified base recovery, final checkpoint/hash propagation, and non-leakage of private state into the event payload.

Unit/fake-session results prove coordinator and SQL construction behavior only. They do not prove a deployed PostgreSQL migration, RLS/effective privileges, or process-crash recovery.

## Release status

The permanent `COMMAND_IN_PROGRESS` behavior has been replaced by an attempt-fenced recovery protocol in source. MP-3 nevertheless remains **NO-GO / not release-ready** until the environment-backed lanes below pass.

## Infrastructure lanes — BLOCKED / NOT RUN

`AISCRIPTKILL_MP3_RECOVERY_DB_URL` was not available, so the real PostgreSQL tests were skipped. The following are still required before removing the release blocker:

- apply the forward migration to a disposable PostgreSQL/Supabase database, including duplicate-processing preflight fixtures;
- verify RLS, grants, and effective browser-role privileges;
- run concurrent reclaim and stale-writer races against real database connections;
- run cross-process crash injection after claim, after the first command checkpoint, after quiescence, before final commit, and after commit before the HTTP response;
- prove exactly one revision, event, projection effect, terminal receipt, checkpoint ID, and final state hash across restart.

Legacy processing receipts without provable private base state/checkpoint lineage must be reconciled explicitly by an operator. They are not automatically replayed, assigned lineage by timestamp, or moved to a new command UUID.
