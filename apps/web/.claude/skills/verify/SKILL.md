---
name: verify
summary: Drive the Next.js multiplayer UI with Playwright route mocks and capture screenshots.
---

# Web runtime verification

1. Start Next with the same public auth configuration used by `playwright.config.ts`, on an unused port:
   `NEXT_PUBLIC_SUPABASE_URL=http://127.0.0.1:54321 NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY=playwright-public-anon-key NEXT_PUBLIC_USE_MOCK=false npm --prefix apps/web run dev -- --hostname 127.0.0.1 --port <port>`
2. Use a standalone Playwright browser script, not the test runner. Route `**/auth/v1/signup` and `**/api/v1/**` with participant-safe fixtures from `e2e/multiplayer-gameplay.spec.ts`.
3. Navigate to `/play/<session-id>/lobby`, drive the visible controls, record request counts, and save a temporary screenshot under `artifacts/`.
4. For multiplayer stage interactions, capture `.mansion-demo` pose attributes before and after the action. Use a restored `players[].scene_x/scene_y` snapshot when verifying a location-specific shortcut.
5. Stop the temporary dev server and remove screenshots unless the repository has an explicit visual-baseline policy.
