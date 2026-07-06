# Frontend Architecture

## Stack And App Shell

The frontend lives in `apps/web`. `apps/web/package.json` defines a Next.js 15, React 19, TypeScript app with Zustand, TanStack Query, framer-motion, Howler, Konva/react-konva, sonner, lucide-react, and Tailwind-related tooling.

`apps/web/app/layout.tsx` wraps the app with a TanStack Query provider and global styling from `apps/web/app/globals.css`. `apps/web/app/page.tsx` redirects visitors to `/library`.

The design intent is in `/docs/FRONTEND_EXPERIENCE_DESIGN.md` and `/docs/SONNET5_HANDOFF.md`: the app should feel like an immersive interactive film, with scene backgrounds, restrained overlays, audio/animation feedback, and mystery-focused flow rather than a generic chat UI.

## Route Map

Current pages:

- `/library`: `apps/web/app/library/page.tsx`. Shows a hard-coded Snow Village library experience rather than querying live packages.
- `/library/[id]`: `apps/web/app/library/[id]/page.tsx`. Calls `api.getPackage(scriptId)` and renders details with mock character previews.
- `/play/[sessionId]/select`: `apps/web/app/play/[sessionId]/select/page.tsx`. The segment is named `sessionId`, but the page treats it as a script id and creates a local `session-{Date.now()}` route after character selection.
- `/play/[sessionId]`: `apps/web/app/play/[sessionId]/page.tsx`. Main gameplay screen. It uses Zustand plus `getMockEngine`, `mockScenes`, and `MockWsClient` directly.
- `/play/[sessionId]/review`: `apps/web/app/play/[sessionId]/review/page.tsx`. Calls `api.getReview(sessionId)` and renders score, correctness, missed clues, clue coverage, player path, and actions.

The intended product flow from the design doc is:

```text
/library -> /library/{script_id} -> /play/{script_id}/select -> /play/{session_id} -> /play/{session_id}/review
```

## State Management

`apps/web/stores/gameStore.ts` is the shared Zustand store for gameplay UI state. It tracks:

- Session identity: `sessionId`, `scriptId`, `playerCharacterId`.
- Progress: `currentStage`, `currentScene`, available actions, characters, scenes.
- Player discoveries: unlocked clues, discovered evidences, cards.
- Chat state: messages and typing indicator.
- Media state: current BGM and playback flag.
- UI state: active panel, selected hotspot, transitions.

The store is in-memory only. Refreshing the page loses state unless the mock engine or backend reload path reconstructs it.

## API And WebSocket Boundary

`apps/web/lib/api.ts` is the live/mock REST client. Its methods cover session create/get/update, actions, final submission, clues, evidences, characters, chat history, cards, review, package list, and package detail. In the browser, mock mode is on unless `NEXT_PUBLIC_USE_MOCK === "false"`.

`apps/web/lib/ws.ts` is the live WebSocket client. It connects to the same browser host at `/api/v1/ws/{sessionId}`, dispatches events by `message.type`, reconnects automatically, and sends `session.ping` every 30 seconds.

`apps/web/lib/mock-ws.ts` simulates richer gameplay events for the current UI. The backend WebSocket currently only accepts `session.ping` and emits `session.pong`, so do not expect live server event parity yet.

## Gameplay UI Composition

The main gameplay page layers the experience roughly as:

- Full-screen background via `SceneBackground`.
- Hotspot interaction via `SceneHotspots`.
- Top action/navigation bar.
- Bottom chat/visual-novel panel via `ChatPanel`.
- Modal or sheet-like overlays for `ClueBoard`, `EvidenceBackpack`, `FinalSubmission`, and `TruthReveal`.
- `StageTransition`, flash/tension visual effects, and toast feedback.

Several components call the mock engine directly, including `ChatPanel`, `SceneHotspots`, `EvidenceBackpack`, and `FinalSubmission`. That makes the current gameplay surface useful for UX iteration but not representative of live backend integration.

## Mock Data Domain

`apps/web/lib/mock-data.ts` contains a substantial Snow Village scenario: package metadata, characters, stages, scenes, hotspots, clues, evidences, dialogue reactions, stage progression, final scoring, and review generation. It is currently the richest executable game content in the repository.

There is a known content inconsistency: mock final scoring treats `chengjun` as correct, while truth reveal copy in the game page names `wangdada` as the real killer. Resolve this before using mock content as canonical package data.

## Change Guidance

When changing library/detail/review pages, decide whether the page should remain mock-friendly or become live-first through `apps/web/lib/api.ts`.

When changing main gameplay, be explicit about the integration target:

- Mock UX only: update `mock-data.ts`, `mock-ws.ts`, and the direct component calls.
- Live integration: route actions through `api.performAction` or `WsClient`, update store from real responses, and account for the backend's currently limited action and WebSocket behavior.
- Product route correctness: consider renaming or refactoring `/play/[sessionId]/select` because it receives a script id before a session exists.

When adding visual features, align with `/docs/FRONTEND_EXPERIENCE_DESIGN.md` and the existing component style rather than creating a separate design language.
