# Backend Architecture

## Entry Point And Middleware

The backend entrypoint is `engine/api/main.py`. `create_app()` builds the FastAPI app with:

- Custom `ApiError` and database exception handlers from `engine/api/errors.py`.
- In-memory per-client rate limiting from `engine/api/middleware/rate_limit.py`.
- CORS origins from `engine/api/config.py`.
- Routers from `engine/api/routes/sessions.py`, `actions.py`, `packages.py`, and `engine/api/websocket/handler.py`.
- `/health` and `/health/db` endpoints.

`/health/db` calls `engine/db/session.py::check_database_connection()`, which verifies connection and the presence of required public tables, including `script_knowledge` from the vector migration.

## Configuration

`engine/api/config.py` uses Pydantic settings and expects Supabase/database variables such as `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY`, `SUPABASE_SECRET_KEY`, `DATABASE_URL`, optional `DATABASE_POOLER_URL`, `CORS_ORIGINS`, and `RATE_LIMIT_PER_MINUTE`.

Important current caveat: settings point at the repo `.env.example` as the env file, and this worktree's sample file contains project-specific Supabase/database configuration. Do not copy those values into frontend code or public docs; provide real runtime configuration through the deployment environment.

Database connection uses `DATABASE_POOLER_URL` when present, otherwise `DATABASE_URL`. Plain `postgresql://` URLs are converted to `postgresql+asyncpg://`, and connections use `ssl=require`.

## Authentication And Authorization

`engine/api/middleware/auth.py` defines the route dependency used across routes:

- No bearer token: returns `CurrentUser(subject="anonymous", role="anonymous")`.
- Bearer token: verifies a Supabase JWT against the project JWKS and returns authenticated current user.
- Package import and package status updates use an admin-only dependency. The backend only trusts Supabase `app_metadata.role` / `app_metadata.roles` for this decision; browser-supplied user metadata is not used for authorization.

Session access is enforced in `engine/services/session_service.py`. If `game_sessions.player_id` is `NULL`, access is allowed to anyone who knows the session UUID. If `player_id` is set, it must match the authenticated Supabase user id.

Database-level RLS policies exist in `supabase/migrations/004_rls_policies.sql`, but backend server-side access patterns and service role usage need to be considered when extending authorization.

## API Routes

### Sessions

`engine/api/routes/sessions.py` exposes:

- `POST /api/v1/sessions`: create a session from a published script package and preferred character.
- `GET /api/v1/sessions/{session_id}`: return current session state summary.
- `PATCH /api/v1/sessions/{session_id}`: restore a checkpoint.
- `GET /api/v1/sessions/{session_id}/clues`: unlocked clues.
- `GET /api/v1/sessions/{session_id}/evidences`: discovered evidences.
- `GET /api/v1/sessions/{session_id}/characters`: currently available characters.
- `GET /api/v1/sessions/{session_id}/chat-history`: stored chat history.
- `GET /api/v1/sessions/{session_id}/cards`: usable cards, derived from evidence rows with card types.
- `GET /api/v1/sessions/{session_id}/review`: completed review.

### Actions

`engine/api/routes/actions.py` exposes:

- `POST /api/v1/sessions/{session_id}/actions`
- `POST /api/v1/sessions/{session_id}/final-submission`

The current action handler maps action types in `engine/services/action_mappers.py`. It is deterministic placeholder logic, not AI-driven and not yet fully package-driven.

### Packages

`engine/api/routes/packages.py` exposes:

- `POST /api/v1/packages`: upload and import a zip archive. Optional `publish=true` publishes on import.
- `PATCH /api/v1/packages/{package_id}`: update package status.
- `GET /api/v1/packages`: list published packages for the frontend library.

The first two package endpoints are backend-admin operations. Frontend clients must call the FastAPI API and provide an admin Supabase Auth JWT; they must not write to Supabase tables directly.

Package import replaces all structure rows for a script id after upserting the package record.

### WebSocket

`engine/api/websocket/handler.py` accepts `/api/v1/ws/{session_id}` and currently supports heartbeat only: receive `session.ping`, send `session.pong` with the session id. It does not yet stream gameplay events.

## Service And Repository Layers

The backend follows a route -> service -> repository split.

`engine/services/session_service.py` coordinates session lifecycle, action execution, final submission, and data queries. It delegates persistence to `engine/repositories/session_repository.py`, which delegates to focused modules:

- `session_seed.py`: derive initial runtime state from a published package, entry stage, playable characters, and stage definition defaults.
- `session_mutations.py`: create sessions/checkpoints, restore checkpoints, apply action effects, upsert discoveries, save submissions/reviews.
- `session_queries.py`: load sessions, stages, discoveries, characters, chat, cards, reviews.
- `session_context.py`: set Postgres settings such as `app.current_stage` and `app.player_character` before visibility-sensitive queries.
- `session_models.py` and `session_rows.py`: runtime state and row mapping.

`engine/services/import_service.py` validates uploaded package zips through `engine/core/package_loader.py` and writes them through `engine/repositories/package_import_repository.py`.

`engine/services/package_service.py` lists and updates package status through package repositories.

## Current Gameplay Behavior

Current `action_mappers.py` behavior is intentionally simple:

- `talk_to_npc`: returns a canned Wang Dada-style reply and persists player/NPC chat messages.
- `examine_scene`: discovers fixed clue `broken_glass`, updates unlocked clues/current scene, and persists a discovery.
- `show_evidence` and `use_card`: return canned responses with no meaningful state mutation.
- `request_advance`: always transitions from `act1_investigation` to `act1_event` with fixed actions.
- `open_clue_board`: returns `advance_denied` explaining that the frontend should open a local view and call the clues endpoint.
- Final submission: score is `min(100, 55 + 10 * len(key_evidences))`, `correct=True`, with fixed missed evidence ids and ending id.

Do not treat this as final business logic.

## Skeleton Areas

The docs and dependencies mention LangGraph, agents, RAG, media orchestration, condition DSL, and scoring. Current implementation is mostly skeletal in:

- `engine/agents/`
- `engine/rag/`
- `engine/media/orchestrator.py`
- `engine/core/script_engine.py`
- `engine/core/condition_evaluator.py`
- `engine/core/event_bus.py`
- `engine/core/checkpoint.py`
- `engine/services/scoring_service.py`

Future work should integrate these through the existing service/repository boundaries instead of bypassing persistence and authorization.
