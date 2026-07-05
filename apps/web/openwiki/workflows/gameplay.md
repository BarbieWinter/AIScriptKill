# Gameplay Workflow

This page describes the user-facing product journey represented by the current frontend source. It documents what exists in the UI today and where integration is still pending.

## Product Concept

The app presents an AI-assisted script-kill experience: a player chooses a mystery script, takes on a character identity, investigates scenes, talks with NPCs or the DM, collects clues/evidence/cards, submits a final answer, and receives a review score.

The current hardcoded story is `雪乡连环杀人事件`, a Snow Village murder mystery. The library and detail pages describe a snowy northeastern village, New Year setting, serial murders, investigation, dialogue, and hidden secrets.

## Route Flow

1. Root redirect

   [`app/page.tsx`](../../app/page.tsx) immediately redirects `/` to `/library`.

2. Script library

   [`app/library/page.tsx`](../../app/library/page.tsx) renders a sticky header, a hero section for `雪乡连环杀人事件`, and a script card grid. The component currently initializes a single package via `setPackages(...)` inside `useEffect`. A source TODO says this should later fetch from `GET /api/v1/packages`.

3. Script detail

   [`app/library/[id]/page.tsx`](../../app/library/[id]/page.tsx) reads `params.id` as `scriptId`, then renders story metadata, synopsis, six character previews, and a start link to `/play/${scriptId}/select`.

4. Character selection

   [`app/play/[sessionId]/select/page.tsx`](../../app/play/[sessionId]/select/page.tsx) renders six selectable identity cards and a confirm button. The buttons currently do not store a selected character or call the backend. Character ids in this file are hardcoded (`zhuosiyuan`, `cuikaiqiang`, `likaiin`, `wangqi`, `xiaomeng`, `chenji`).

5. Main play surface

   [`app/play/[sessionId]/page.tsx`](../../app/play/[sessionId]/page.tsx) reads `params.sessionId`, then renders a full-screen layered game UI:

   - scene background layer
   - placeholder layer for scene hotspots, intended for Konva
   - top action bar with `线索板`, `背包`, and `笔记`
   - bottom dialogue/narration panel
   - text input with examples for `@角色名`, `/dm`, and evidence presentation
   - bottom status line with music/time text

   The page does not currently use `sessionId`, `WsClient`, `api.performAction`, or the Zustand store.

6. Case review

   [`app/play/[sessionId]/review/page.tsx`](../../app/play/[sessionId]/review/page.tsx) renders a static score, correct answer block, missed clue block, truth summary, and replay/share buttons. It does not yet call `api.getReview`.

## Domain Objects in the Frontend

The product workflow is supported by shared interfaces in [`types/index.ts`](../../types/index.ts):

- `ScriptPackage`: published mystery package metadata, including title, description, difficulty, duration, genre, and status.
- `GameSession`: session id, script id, status, current stage, player character, available actions, and current scene.
- `Character`: playable/NPC identity with optional portrait/personality fields.
- `Clue` and `Evidence`: investigation artifacts with discovery/viewing status.
- `Stage`: game phase with action and character availability.

The local store in [`stores/gameStore.ts`](../../stores/gameStore.ts) expands this into runtime UI state for chat, panels, media, transitions, and unlocked objects.

## Integration Gaps to Watch

- Library data should eventually come from `api.getPackages` or an equivalent helper; no such helper exists yet in [`lib/api.ts`](../../lib/api.ts), even though the page TODO names the endpoint.
- Starting a game should likely call `api.createSession(scriptId, characterId)` before navigating to `/play/[sessionId]`.
- Character selection currently sits under a `[sessionId]` route but receives a script id from the detail page link. Decide and document the intended lifecycle before wiring backend calls.
- The play screen should subscribe to realtime events through [`lib/ws.ts`](../../lib/ws.ts) and reconcile incoming events into [`stores/gameStore.ts`](../../stores/gameStore.ts).
- Review should load from `api.getReview(sessionId)` and should handle completed/abandoned session states.

## Change Guidance

When adding a workflow feature, update the flow from front to back:

- Start with the route page and the exact user action being added.
- Add or type the necessary API helper in `lib/api.ts`.
- Update `types/index.ts` if the backend returns new domain fields.
- Use `useGameStore` for cross-panel gameplay state instead of isolated component state.
- Re-run build/type validation after route param or shared type changes.
