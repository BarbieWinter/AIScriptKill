# System Architecture

## Architectural Intent

The intended architecture is documented in `/docs/ARCHITECTURE_OVERVIEW.md`: a reusable Script Engine loads pluggable Script Packages. Game logic belongs in the engine; story content, stage rules, clues, characters, scenes, media, and DM guidance belong in package YAML/assets. `/doc/剧本系统设计.md` adds the product boundary: AI performs and controls flow inside a fixed mystery, but should not rewrite the culprit, motive, or key evidence.

## Runtime Shape Today

Current source is a partial implementation of that target architecture.

```text
Next.js web app
  -> REST /api/v1 and WebSocket contract wrappers
  -> FastAPI backend
  -> service layer
  -> repository layer
  -> Supabase/Postgres tables and RLS

Frontend main gameplay path
  -> mock data and MockWsClient directly
```

The live backend entrypoint is `engine/api/main.py`. It creates the FastAPI app, installs custom API/database error handlers, rate limiting, CORS, routers for sessions/actions/packages, WebSocket routing, and `/health` plus `/health/db`.

The live frontend entrypoint is `apps/web/app/page.tsx`, which redirects to `/library`. App-wide providers and layout live in `apps/web/app/layout.tsx`.

## Major Components

### Frontend

`apps/web` is a Next.js App Router application with TypeScript, React 19, Zustand, TanStack Query, framer-motion, Howler, Konva/react-konva, lucide-react, and Tailwind. The product route flow is:

```text
/library
/library/[id]
/play/[sessionId]/select
/play/[sessionId]
/play/[sessionId]/review
```

The API wrapper in `apps/web/lib/api.ts` matches the documented `/api/v1` contract and supports mock mode. The WebSocket wrapper in `apps/web/lib/ws.ts` connects to `/api/v1/ws/{sessionId}` and sends periodic `session.ping` messages. The main gameplay page currently bypasses those live wrappers for core play and imports `getMockEngine`, `mockScenes`, and `MockWsClient`.

See [Frontend Architecture](frontend.md).

### FastAPI Gateway

The backend exposes these route groups under `/api/v1`:

- `/sessions`: create/get/restore sessions and query clues, evidences, characters, chat history, cards, and review.
- `/sessions/{session_id}/actions`: perform gameplay action.
- `/sessions/{session_id}/final-submission`: submit final deduction and persist review records.
- `/packages`: import zip package archives, update package status, and list published packages.
- `/ws/{session_id}`: heartbeat-only WebSocket skeleton.

Authentication is optional at the API dependency level. `engine/api/middleware/auth.py` returns an anonymous user when there is no bearer token and validates Supabase JWTs when a token is present.

See [Backend Architecture](backend.md).

### Package And Runtime Services

Script package import is implemented as:

```text
UploadFile zip
  -> engine/services/import_service.py
  -> engine/core/package_loader.py
  -> Pydantic YAML models in engine/core/package_schema.py
  -> engine/repositories/package_import_repository.py
  -> script_* structure tables
```

Session runtime is implemented as:

```text
route
  -> engine/services/session_service.py
  -> engine/repositories/session_repository.py
  -> focused session_* repository modules
  -> game_sessions.state JSONB, checkpoints, chat, discoveries, submissions, reviews
```

`engine/services/action_mappers.py` is currently deterministic placeholder gameplay logic. It returns canned NPC replies, scene discoveries, stage transition patches, and final scoring.

### Data Platform

Supabase/Postgres schema is in `supabase/migrations/`:

- `001_script_tables.sql`: package, stage, character, clue, evidence, scene, and media tables.
- `002_runtime_tables.sql`: game sessions, checkpoints, chat messages, discoveries, final submissions, reviews.
- `003_vector_tables.sql`: `script_knowledge` pgvector table for future RAG.
- `004_rls_policies.sql`: RLS policies for service role, authenticated player access, and stage/character visibility.
- `005_runtime_persistence_indexes.sql`: indexes for sessions, packages, submissions, reviews, checkpoints, and card/evidence queries.
- `006_api_role_privileges.sql`: grants and public published-package policy.

`engine/db/session.py` creates an async SQLAlchemy engine using `DATABASE_POOLER_URL` first, then `DATABASE_URL`, and requires SSL.

### AI, RAG, Media, And LangGraph

The repo names and docs point toward LangGraph, DM/NPC/Guard/Hint agents, RAG retrieval, and media orchestration. Current source does not yet wire these into gameplay. Representative skeleton files include `engine/agents/*.py`, `engine/rag/*.py`, `engine/media/orchestrator.py`, `engine/core/script_engine.py`, `engine/core/condition_evaluator.py`, and `engine/services/scoring_service.py`.

When adding these features, do not assume the documented architecture is already active. Start from the real route/service/repository flow and introduce integrations deliberately.

## Important Cross-Cutting Constraints

- Spoiler control is a core product requirement. RLS policies and package metadata fields like `stage_visible`, `visibility`, and `character_id` exist to prevent premature disclosure, but application-level behavior is still incomplete.
- The backend currently permits anonymous sessions with `player_id = NULL`; `session_service._assert_session_access` allows access to those sessions if the UUID is known.
- The frontend and backend both know the API contract, but active gameplay is still mock-first.
- Existing docs may describe intended acceptance criteria, not current behavior. Source wins when they conflict.
