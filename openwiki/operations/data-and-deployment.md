# Data And Operations

## Environment And Configuration

Backend configuration lives in `engine/api/config.py`. It expects these environment variables:

- `SUPABASE_PROJECT_REF` optional.
- `SUPABASE_URL`.
- `SUPABASE_PUBLISHABLE_KEY`.
- `SUPABASE_SECRET_KEY`.
- `DATABASE_URL`.
- `DATABASE_POOLER_URL` optional, preferred at runtime when present.
- `CORS_ORIGINS`, defaulting to local frontend origins.
- `RATE_LIMIT_PER_MINUTE`, defaulting to 120.

Current caveat: this checkout intentionally reads `.env.example` for backend runtime configuration, and the file currently contains project-specific Supabase/database configuration. Treat it as sensitive local configuration; frontend Supabase variables are not declared there, and browser code must use the FastAPI `/api/v1` surface instead of direct database access.

The backend database engine is async SQLAlchemy with asyncpg. `engine/db/session.py` converts `postgresql://` to `postgresql+asyncpg://`, uses pool pre-ping, small pool sizing, and `ssl=require`.

## Supabase/Postgres Schema

Migrations under `supabase/migrations/` define the database shape:

- `001_script_tables.sql`: script package structure tables: packages, stages, characters, clues, evidences, scenes, media.
- `002_runtime_tables.sql`: runtime tables: sessions, checkpoints, chat messages, discoveries, final submissions, reviews.
- `003_vector_tables.sql`: `script_knowledge` pgvector table for future RAG with a 1536-dimensional embedding column and IVFFlat index.
- `004_rls_policies.sql`: RLS enablement and policies for service-role access, authenticated player-owned session data, and stage/character-filtered script content.
- `005_runtime_persistence_indexes.sql`: supplemental indexes for session/package/status/review/checkpoint/card queries.
- `006_api_role_privileges.sql`: grants for anon/authenticated/service_role and a public policy for published packages.

`engine/db/tables.py` mirrors most public tables for SQLAlchemy Core queries. Keep migrations and table metadata aligned when changing schema.

## RLS And Permissions

RLS is central to spoiler control. The current policy design includes:

- Full access for `service_role` across script and runtime tables.
- Published package visibility for anon/authenticated users via `006_api_role_privileges.sql`.
- Authenticated players can access their own sessions and related runtime data.
- Clue/evidence/scene visibility can depend on current stage and player character settings.
- `script_knowledge` is explicitly not intended for direct player queries; RAG should query server-side and enforce stage/role context.

Application-level behavior must still be reviewed carefully. Anonymous backend sessions currently use `player_id = NULL` and are allowed by service-layer access checks if the UUID is known.

Backend package import and package status changes are additionally protected by an admin-only FastAPI dependency. The dependency trusts Supabase `app_metadata`, not user-editable metadata.

## Local Development

README documents `make install`, `make dev`, `make dev-web`, and `make test`, but the root `Makefile` is currently empty. Use direct commands until the Makefile is restored.

Backend:

```bash
uvicorn engine.api.main:app --reload
pytest
```

Frontend:

```bash
npm --prefix apps/web install
npm --prefix apps/web run dev
npm --prefix apps/web run build
npm --prefix apps/web run start
npm --prefix apps/web run lint
```

Docker Compose exists in `docker-compose.yml` with services for `engine`, `web`, and a local Supabase image. It references `engine/Dockerfile` and `apps/web/Dockerfile`; verify those Dockerfiles exist before relying on compose. Compose also expects `.env`, which should contain local secrets and must not be documented.

## Testing Status

Configured backend test settings are in `pyproject.toml`:

- Test path: `engine/tests`.
- `pytest-asyncio` mode: auto.
- Ruff target: Python 3.12, line length 100, selected lint families `E`, `F`, `I`, `N`, `W`.

Current `engine/tests` includes admin authorization tests for package import/status management in `engine/tests/test_admin_auth.py`. There is still no broad backend coverage for package loading, persistence, gameplay actions, or RLS-sensitive queries.

Frontend scripts include build and lint commands, but no explicit test runner is configured in `apps/web/package.json`.

When adding tests, prioritize:

- Package archive validation and import replacement behavior.
- Session creation from imported package fixtures.
- Action side effects and checkpoint persistence.
- RLS-sensitive query behavior if tests can run against Supabase/Postgres.
- Frontend route behavior around mock/live boundaries and session creation.

## Operational Caveats

- `.env.example` is used by the backend config in this checkout and currently contains project-specific Supabase/database configuration; treat it as sensitive local configuration and do not expose those values to browser code or public docs.
- `Makefile` is empty while README references make commands.
- Docker Compose references Dockerfiles that were not confirmed during this pass.
- Existing root git status includes unrelated `.DS_Store` changes and deleted old `apps/web/openwiki` files; do not revert user changes unless explicitly asked.
- The backend health check requires `script_knowledge`; make sure vector migrations are applied before using `/health/db`.
- Direct table access and backend API access have different security models. Keep RLS, service-role usage, and app-level checks in sync.
