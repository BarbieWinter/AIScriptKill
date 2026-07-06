# OpenWiki Quickstart

## What This Repository Is

AIScriptKill is an AI-assisted immersive murder-mystery game system. The product direction is a fixed, high-quality script package plus AI performance, stage control, clue/evidence discovery, media atmosphere, final deduction, and review. The clearest product statement is in `/doc/剧本系统设计.md`: AI should perform inside a fixed script boundary, not rewrite the mystery, change the culprit, or invent key evidence.

The repository currently contains four major areas:

- `engine/`: Python 3.12 FastAPI backend, package import/runtime persistence services, Supabase/Postgres access, and skeleton AI/RAG/media modules.
- `apps/web/`: Next.js 15 React 19 frontend for library browsing, character selection, gameplay, and review.
- `supabase/migrations/`: Postgres schema, pgvector knowledge table, RLS policies, indexes, and API role grants.
- `docs/` and `doc/`: existing architecture, API, package schema, frontend design, execution plan, and Chinese product/domain design docs.

Recent git history shows the repo was built in layers: initial product/assets import, system scaffold, frontend architecture, and backend architecture. The current worktree also contains substantial uncommitted backend persistence work and deleted older `apps/web/openwiki` docs. This OpenWiki is intentionally rooted at `/openwiki`.

## Current Implementation Reality

Treat the existing design docs as important intent, but verify behavior in source before changing code.

Implemented now:

- FastAPI app assembly, CORS, rate limiting, error handling, session/package/action routes, and WebSocket heartbeat in `engine/api/`.
- Async SQLAlchemy access to Supabase/Postgres in `engine/db/session.py` and table metadata in `engine/db/tables.py`.
- Script package zip import and YAML validation in `engine/core/package_loader.py`, `engine/core/package_schema.py`, and `engine/services/import_service.py`.
- Runtime session creation, checkpoint restore, deterministic action effects, final submission persistence, and review lookup through `engine/services/` and `engine/repositories/`.
- Next.js pages for `/library`, `/library/[id]`, `/play/[sessionId]/select`, `/play/[sessionId]`, and `/play/[sessionId]/review`.
- Frontend mock gameplay data and mock WebSocket in `apps/web/lib/mock-data.ts` and `apps/web/lib/mock-ws.ts`.

Mostly aspirational or placeholder today:

- LangGraph state machine, condition evaluator, event bus, checkpoint abstraction, AI agents, RAG retriever/chunker/reranker, media orchestrator, and scoring service are skeletons or comment-only modules.
- Main frontend gameplay directly imports mock engine/mock WebSocket instead of live backend REST/WS.
- `script-packages/snow-village` has the expected directory skeleton but no `package.yml` or YAML content.
- Root `Makefile` is empty even though README implies setup commands.
- `.env.example` contains project-specific Supabase/database configuration in this worktree; treat it as sensitive local configuration, not a template for frontend or public docs.

## Where To Start

- Architecture overview: [System Architecture](architecture/system.md)
- Frontend route/UI behavior: [Frontend Architecture](architecture/frontend.md)
- Backend API/service/runtime behavior: [Backend Architecture](architecture/backend.md)
- Product and script package model: [Script And Gameplay Domain](domain/script-gameplay.md)
- Player and package workflows: [Gameplay And Package Workflows](workflows/gameplay-and-packages.md)
- Supabase, config, deployment, testing: [Data And Operations](operations/data-and-deployment.md)

Existing primary docs remain useful:

- `/docs/ARCHITECTURE_OVERVIEW.md`: target architecture and philosophy.
- `/docs/API_REFERENCE.md`: REST and WebSocket contract, though live source is the authority.
- `/docs/SCRIPT_PACKAGE_SCHEMA.md`: intended package authoring schema.
- `/docs/CONDITION_DSL_REFERENCE.md`: intended stage/event condition language.
- `/docs/FRONTEND_EXPERIENCE_DESIGN.md`: route flow and immersive UX design.
- `/docs/EXECUTION_PLAN.md`: task roadmap and intended acceptance criteria.
- `/doc/剧本系统设计.md`: product/domain positioning and content boundary rules.

## Local Commands

Documented commands in `README.md` are:

```bash
make install
make dev
make dev-web
make test
```

However, the root `Makefile` is currently empty. Until it is restored, use the underlying tools directly:

```bash
# Backend, after installing Python dependencies from pyproject.toml
uvicorn engine.api.main:app --reload

# Frontend
npm --prefix apps/web install
npm --prefix apps/web run dev

# Backend tests, if tests are added
pytest
```

The frontend package also provides:

```bash
npm --prefix apps/web run build
npm --prefix apps/web run start
npm --prefix apps/web run lint
```

Be aware that `next lint` is configured in `apps/web/package.json`, but modern Next.js versions may require updating lint commands depending on installed tooling.

## Change Guidance For Future Agents

Before backend changes, read [Backend Architecture](architecture/backend.md), [Data And Operations](operations/data-and-deployment.md), and the relevant route/service/repository files. Most runtime behavior now lives in services and repositories, not in the LangGraph skeleton.

Before frontend changes, read [Frontend Architecture](architecture/frontend.md). Decide explicitly whether the change belongs to mock gameplay, the live `api` wrapper, or the eventual integration between them.

Before package/content changes, read [Script And Gameplay Domain](domain/script-gameplay.md), `/docs/SCRIPT_PACKAGE_SCHEMA.md`, and `engine/core/package_loader.py`. The loader currently imports zip archives, not loose package directories.

Before relying on README commands or environment setup, inspect the current `Makefile`, `.env.example`, and `engine/api/config.py`; the current config reads Supabase/database variables from the environment or `.env.example`, and this worktree's `.env.example` should be treated as sensitive local configuration.
