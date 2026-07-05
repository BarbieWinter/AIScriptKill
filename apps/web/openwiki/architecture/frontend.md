# Frontend Architecture

## Stack and Package Shape

The frontend is a Next.js 15 App Router application using React 19, TypeScript, Tailwind CSS 4, and Zustand. Dependencies in [`package.json`](../../package.json) also include React Query, Howler, Konva/React-Konva, Lucide icons, and class utility packages, but the inspected page components do not yet use most of those runtime libraries.

The TypeScript config is strict and uses the `@/*` path alias to resolve from the package root, as defined in [`tsconfig.json`](../../tsconfig.json). The package has no custom source directory; app, library, store, and type files live at the package root.

## Routing Model

The app uses App Router filesystem routes under [`app/`](../../app):

- [`app/page.tsx`](../../app/page.tsx) redirects root traffic to `/library`.
- [`app/library/page.tsx`](../../app/library/page.tsx) renders the script library.
- [`app/library/[id]/page.tsx`](../../app/library/[id]/page.tsx) renders a script detail page for a dynamic `id` route param.
- [`app/play/[sessionId]/select/page.tsx`](../../app/play/[sessionId]/select/page.tsx) renders character selection under a play session path.
- [`app/play/[sessionId]/page.tsx`](../../app/play/[sessionId]/page.tsx) renders the main play surface.
- [`app/play/[sessionId]/review/page.tsx`](../../app/play/[sessionId]/review/page.tsx) renders the case review screen.

The current dynamic routes read params where needed, but several screens are not yet semantically consistent with their route names. For example, character selection is nested under `[sessionId]`, while the detail page links to `/play/${scriptId}/select`; in current source this path segment behaves more like a script id until real session creation is wired.

## Client Components and State

Every substantive route page inspected begins with `"use client"`, so the current UI is client-rendered and can use browser APIs, hooks, and interactive state directly.

[`stores/gameStore.ts`](../../stores/gameStore.ts) defines a Zustand store for session state, game progress, available actions, unlocked clues, discovered evidence, chat messages, media state, active panels, selected hotspots, and scene/stage transitions. It also defines the frontend action vocabulary:

- `talk_to_npc`
- `examine_scene`
- `show_evidence`
- `use_card`
- `open_clue_board`
- `request_advance`

The store is not imported by any inspected page yet. When wiring gameplay, prefer making route pages read/write through this store instead of duplicating state locally.

## Shared Types

[`types/index.ts`](../../types/index.ts) defines frontend-facing interfaces for `ScriptPackage`, `GameSession`, `Character`, `Clue`, `Evidence`, and `Stage`. These names match the product domain and the API helper methods, but the API client currently returns `any`. Future integration work should tighten return types in [`lib/api.ts`](../../lib/api.ts) against these interfaces or backend-generated schemas.

## Styling and Theme Tokens

[`app/globals.css`](../../app/globals.css) imports Tailwind CSS and defines a dark theme through CSS variables:

- base colors: `--background`, `--foreground`, `--muted`, `--border`, `--accent`
- script-overridable theme colors: `--theme-primary`, `--theme-secondary`, `--theme-accent`
- semantic colors: `--danger`, `--warning`, `--success`, `--info`
- layered surfaces: `--overlay`, `--panel-bg`, `--scene-overlay`

The same file provides animation utility classes and domain-specific text/emotion classes such as `.dm-narration`, `.npc-emotion-shaken`, `.npc-emotion-fear`, and `.npc-emotion-lying`.

[`app/layout.tsx`](../../app/layout.tsx) sets `lang="zh-CN"`, applies the `dark` class to `<html>`, and sets Chinese metadata for an AI immersive suspense game.

## Utility Layer

[`lib/utils.ts`](../../lib/utils.ts) exposes `cn(...)`, a small `clsx` plus `tailwind-merge` helper for composing Tailwind class names. Existing pages mostly use literal class strings; use `cn` when conditional classes appear.

## Change Notes

- Treat the pages as product scaffolds until they are wired to backend data.
- Keep route params semantically clear when introducing real sessions: script ids, character ids, and session ids should not be silently interchangeable.
- If package-specific themes become real, centralize CSS variable overrides near script/package loading rather than spreading color literals across pages.
- The main play screen has comments for scene background, Konva hotspot layer, top controls, dialogue area, and status bar. These comments are a useful outline for adding canvas/media interaction incrementally.
