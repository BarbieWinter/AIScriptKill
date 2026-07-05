# AIScriptKill Web Quickstart

This OpenWiki covers the `apps/web` package only. The workspace root for this run is the Next.js frontend at `/Users/babiwei/Downloads/AIScriptKill/apps/web`; parent-level engine, database, and asset directories are outside this documentation scope.

## What this package is

`aiscriptkill-web` is the frontend shell for an AI-assisted murder mystery / script-kill game. It is a Chinese-language Next.js App Router application for browsing scripts, selecting a player identity, entering an immersive play screen, and reviewing the case outcome. The current UI is mostly a scaffold around the bundled product concept `雪乡连环杀人事件`; backend API and WebSocket helper modules exist, but the page components still use hardcoded content in the inspected source.

Primary source references:

- Package and scripts: [`package.json`](../package.json)
- App metadata and global shell: [`app/layout.tsx`](../app/layout.tsx)
- Root redirect to the library: [`app/page.tsx`](../app/page.tsx)
- Local API rewrite to the backend engine: [`next.config.ts`](../next.config.ts)
- API/WebSocket helpers: [`lib/api.ts`](../lib/api.ts), [`lib/ws.ts`](../lib/ws.ts)
- Frontend game state store: [`stores/gameStore.ts`](../stores/gameStore.ts)

## Start here as a developer or agent

1. Install dependencies from this directory:

   ```bash
   npm install
   ```

2. Run the development server:

   ```bash
   npm run dev
   ```

3. Open the app and begin at `/library`. The root page redirects there automatically.

4. For local backend calls, the Next config rewrites `/api/:path*` to `http://localhost:8000/api/:path*`. A backend server must be running on port 8000 for `lib/api.ts` and `lib/ws.ts` contracts to succeed.

5. Before changing behavior, read the section pages linked below and inspect the source files they cite.

## Documentation Map

- [Frontend Architecture](architecture/frontend.md) explains the App Router structure, styling system, Zustand store, and shared types.
- [Gameplay Workflow](workflows/gameplay.md) maps the user-facing flow from library browsing through case review and marks which parts are currently static.
- [Backend Integration](integrations/backend.md) documents the REST and WebSocket contracts encoded by the frontend.
- [Operations and Testing](operations/testing.md) covers local commands, validation expectations, and known caveats.

## Current Implementation Status

The package was introduced in git commit `7fbba60` as part of a broader build-system architecture scaffold. A scoped git status check for `apps/web` was clean during this OpenWiki init, even though the user-provided status showed dirty files in parent-level backend and root project files.

The frontend currently has these important gaps:

- `app/library/page.tsx` contains a TODO to fetch script packages from `GET /api/v1/packages`, but it currently sets a hardcoded Snow Village package in component state.
- The character select, play, and review screens render static UI and do not yet call `api`, `WsClient`, or `useGameStore`.
- `lib/api.ts`, `lib/ws.ts`, `types/index.ts`, and `stores/gameStore.ts` should be treated as intended contracts and state shape, not proof that all UI flows are wired.
- There are no local test files under `apps/web`; validation is currently based on TypeScript/Next build and lint commands.

## Change Guidance

When changing this app, start from the route page that owns the user workflow, then wire shared contracts only as needed:

- UI layout and route behavior: `app/**/page.tsx`
- Shared data contracts: `types/index.ts`
- Backend calls: `lib/api.ts`
- Realtime session events: `lib/ws.ts`
- Cross-screen game state: `stores/gameStore.ts`
- Global theme tokens and utility animation classes: `app/globals.css`

Keep hardcoded demo content and live backend integration clearly separated. If you replace static data with API data, update the relevant page, shared type definitions, and this wiki together.
