# Operations and Testing

## Local Commands

The package scripts are defined in [`package.json`](../../package.json):

```bash
npm run dev
npm run build
npm run start
npm run lint
```

Use `npm install` or `npm ci` from the `apps/web` directory before running these commands. The lockfile is [`package-lock.json`](../../package-lock.json).

## Development Runtime

`npm run dev` starts the Next development server. The app root redirects to `/library`, implemented in [`app/page.tsx`](../../app/page.tsx).

For backend-dependent work, run the backend engine separately on `localhost:8000`. [`next.config.ts`](../../next.config.ts) rewrites frontend `/api/:path*` requests to `http://localhost:8000/api/:path*`.

The current page components are static enough to render without the backend, but real package loading, session creation, gameplay actions, and review data will require backend availability once wired.

## Build and Type Checking

`npm run build` is the main high-signal validation command because the app uses strict TypeScript settings in [`tsconfig.json`](../../tsconfig.json). It should catch many route, component, and type errors.

Before build validation, watch for these implementation details:

- Several pages are client components and use browser-oriented hooks or APIs.
- `lib/ws.ts` references `window` and `WebSocket`, so instantiate it only from client-side code.
- API helper methods currently return `any`; adding stronger types may surface useful compile-time issues in route pages.

## Lint Caveat

`package.json` defines `"lint": "next lint"`. In modern Next versions this command may be deprecated or unavailable depending on the installed Next CLI behavior. If `npm run lint` fails because `next lint` is unsupported, use the repository's chosen ESLint invocation once one is added, and record that change here.

## Tests

No test files were found under `apps/web` during this OpenWiki init. There is no configured unit, component, or end-to-end test script in `package.json`.

For changes with user-visible behavior, validation should currently include at least:

- `npm run build`
- manual route checks for `/library`, `/library/[id]`, `/play/[sessionId]/select`, `/play/[sessionId]`, and `/play/[sessionId]/review`
- backend contract checks when touching `lib/api.ts`, `lib/ws.ts`, or route pages that call them

## Operational Caveats

- The package has no `.env` requirement in inspected source. Do not read or document real secret files if they appear later.
- `public/` is empty, and current UI uses gradients/placeholders rather than real media assets.
- Dependencies include Howler and Konva, suggesting planned media and interactive scene layers, but the current play screen does not yet initialize them.
- Parent-level files in the larger repository were dirty when this run began, but `git status --short -- .` from `apps/web` showed no local modifications in the documented package.
