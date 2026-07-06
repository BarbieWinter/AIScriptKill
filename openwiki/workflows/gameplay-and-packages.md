# Gameplay And Package Workflows

## Player Gameplay Flow

The intended user journey is documented in `/docs/FRONTEND_EXPERIENCE_DESIGN.md`:

```text
/library
  -> /library/{script_id}
  -> /play/{script_id}/select
  -> /play/{session_id}
  -> /play/{session_id}/review
```

Current frontend implementation mostly follows this shape, but the character selection route is named `/play/[sessionId]/select` while it is actually using that segment as a script id before creating a session.

## Current Frontend Mock Flow

For the active gameplay screen, the richest behavior is frontend-local:

1. `/library` presents Snow Village as a hard-coded script option.
2. `/library/[id]` can use `api.getPackage`, which falls back to mock mode by default in the browser.
3. Character selection uses hard-coded characters and navigates to a generated local session id.
4. `/play/[sessionId]` initializes the Zustand store from `getMockEngine()` and `mockScenes`.
5. `MockWsClient` emits simulated events like chat, clue unlocks, evidence discovery, stage changes, and BGM changes.
6. Components such as `SceneHotspots`, `ChatPanel`, `EvidenceBackpack`, and `FinalSubmission` call the mock engine directly.
7. Review can call `api.getReview`, which uses mock review data unless `NEXT_PUBLIC_USE_MOCK=false`.

This is useful for UX iteration but not yet an end-to-end live backend flow.

## Current Live Backend Session Flow

The implemented backend flow is:

1. Import and publish a script package through `POST /api/v1/packages?publish=true`.
2. Create a session with `POST /api/v1/sessions`, giving `script_id`, `preferred_character_id`, and optional `player_name`.
3. `engine/repositories/session_seed.py` checks that the package is published, finds `engine.entry_stage`, verifies the chosen character is playable, and seeds a `SessionRuntimeState`.
4. `engine/repositories/session_mutations.py` inserts `game_sessions`, creates an `initial` checkpoint, and commits.
5. Game actions go through `POST /api/v1/sessions/{session_id}/actions` and deterministic mappings in `engine/services/action_mappers.py`.
6. Effects persist chat messages, discoveries, state patches, and checkpoints.
7. Final submission goes through `POST /api/v1/sessions/{session_id}/final-submission`, persists `final_submissions` and `reviews`, and marks the session completed.
8. `/review` returns the persisted review.

The live backend does not yet perform AI DM/NPC generation, condition DSL evaluation, package-defined hotspot behavior, or real-time WebSocket event streaming.

## Package Import Workflow

Current import path:

```text
zip upload
  -> packages route
  -> import_service.PackageUpload
  -> load_package_archive(bytes, publish)
  -> PackageImportRepository.import_package()
  -> upsert script_packages
  -> delete existing structure rows
  -> insert stages, characters, clues, evidences, scenes, media
```

Important behavior:

- The archive must be a valid zip.
- Hidden files are filtered by `engine/core/package_archive.py`.
- There must be exactly one `package.yml` path.
- Stages and characters are required.
- Package status is `draft` by default or `published` when the import request uses `publish=true`.
- Re-importing an existing package id replaces structure rows for that package.

## Query Workflow And Spoiler Control

Session data queries load the session first, enforce service-level access, then read package/runtime data:

- Clues and evidences are joined through `session_discoveries`, so only discovered rows are returned by those endpoints.
- Character and card queries use current session state plus stored package data.
- `session_context.py` sets Postgres session settings for current stage and player character before visibility-sensitive queries, matching the RLS design in `supabase/migrations/004_rls_policies.sql`.

RLS policies protect authenticated direct table access, but the backend service itself still needs careful review when introducing service-role access, anonymous sessions, or new query endpoints.

## Workflow Gaps To Watch

- Frontend character selection does not call live `api.createSession` in the inspected implementation.
- Main gameplay does not use live `api.performAction` or `WsClient`; it uses mock engine paths.
- Backend WebSocket only supports heartbeat, while docs and frontend mock expect many gameplay events.
- Backend action behavior is not driven by imported package stage/hotspot/evidence rules yet.
- Backend final scoring is a fixed placeholder.
- `script-packages/snow-village` is not importable as-is because package YAML files are absent.

## Change Guidance

For live integration work, start with one thin vertical slice:

1. Ensure a real package can be imported and published.
2. Make character selection call `api.createSession` and navigate with the returned session id.
3. Make one gameplay action call `api.performAction` and update Zustand from the response.
4. Add backend WebSocket events only after REST state transitions are reliable.
5. Add package-driven rules and condition DSL evaluation after imported package data is complete.

For content workflow work, create package fixtures and loader tests before expanding the schema. The package loader is currently the strongest source of truth for what the backend can ingest.
