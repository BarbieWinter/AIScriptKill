# Backend Integration

The frontend contains two integration layers: a REST helper in [`lib/api.ts`](../../lib/api.ts) and a WebSocket client in [`lib/ws.ts`](../../lib/ws.ts). The current route pages do not yet import these helpers, so this page documents the encoded contracts rather than active end-to-end behavior.

## Local API Routing

[`next.config.ts`](../../next.config.ts) defines a development rewrite:

```ts
source: "/api/:path*"
destination: "http://localhost:8000/api/:path*"
```

The API helper uses `API_BASE = "/api/v1"`, so a frontend call like `/api/v1/sessions` is served through the Next app and forwarded to the local backend at `http://localhost:8000/api/v1/sessions`.

There is no environment-variable based API base URL in the inspected frontend source. Changing backend host/port currently requires editing `next.config.ts` or adding new configuration.

## REST Helper Contract

[`lib/api.ts`](../../lib/api.ts) wraps `fetch` in a `request<T>(method, path, body?)` helper. It always sends `Content-Type: application/json`, JSON-stringifies any truthy body, parses JSON responses, and throws `ApiError` for non-OK responses.

Error responses are expected to look like:

```json
{
  "error": {
    "code": "SOME_CODE",
    "message": "Human readable message",
    "details": {}
  }
}
```

If the backend response does not match that shape, the client falls back to `UNKNOWN_ERROR` and `请求失败`.

Current exported methods:

- `createSession(scriptId, characterId)`: `POST /sessions` with `script_id` and `preferred_character_id`.
- `getSession(sessionId)`: `GET /sessions/{sessionId}`.
- `performAction(sessionId, action, params)`: `POST /sessions/{sessionId}/actions` with an action string and additional params.
- `submitFinal(sessionId, submission)`: `POST /sessions/{sessionId}/final-submission`.
- `getClues(sessionId)`: `GET /sessions/{sessionId}/clues`.
- `getEvidences(sessionId)`: `GET /sessions/{sessionId}/evidences`.
- `getCharacters(sessionId)`: `GET /sessions/{sessionId}/characters`.
- `getChatHistory(sessionId)`: `GET /sessions/{sessionId}/chat-history`.
- `getCards(sessionId)`: `GET /sessions/{sessionId}/cards`.
- `getReview(sessionId)`: `GET /sessions/{sessionId}/review`.

Notable gap: the library page TODO references `GET /api/v1/packages`, but `lib/api.ts` does not currently export a package-list method.

## WebSocket Contract

[`lib/ws.ts`](../../lib/ws.ts) defines `WsClient`, a browser-only class that connects to:

```ts
`${protocol}//${window.location.host}/api/v1/ws/${sessionId}`
```

It derives `ws:` vs `wss:` from the current page protocol and uses the same host as the Next frontend. The `/api` path means local WebSocket behavior depends on the frontend/proxy setup supporting upgrade requests to the backend route.

`WsClient` behavior:

- `connect()` creates a `WebSocket`, starts a 30-second ping loop on open, parses incoming JSON messages, dispatches by `message.type`, and reconnects 3 seconds after close unless destroyed.
- `on(eventType, handler)` registers event handlers and returns an unsubscribe function.
- `off(eventType, handler)` removes a handler.
- `send(type, data)` sends `{ type, data }` only when the socket is open.
- `disconnect()` marks the client destroyed, stops ping/reconnect timers, closes the socket, and clears the reference.
- Heartbeat sends `session.ping` every 30 seconds.

Incoming messages are expected to be JSON objects with at least:

```json
{
  "type": "event.name",
  "data": {}
}
```

No inspected page currently instantiates `WsClient`.

## Shared Type Alignment

[`types/index.ts`](../../types/index.ts) defines frontend interfaces for packages, sessions, characters, clues, evidence, and stages. These should be reconciled with backend schemas before removing `any` return types from `lib/api.ts`.

Important frontend enums/status fields include:

- `ScriptPackage.status`: `draft`, `published`, `archived`
- `GameSession.status`: `in_progress`, `paused`, `completed`, `abandoned`
- `Clue.status`: `locked`, `unlocked`, `discovered`, `viewed`
- `Evidence.status`: `undiscovered`, `discovered`, `viewed`, `deep_viewed`

## Change Guidance

- Add typed API methods before wiring route pages to new endpoints.
- Keep error handling compatible with the `ApiError` shape or update callers and docs together.
- Be careful with WebSocket proxying in Next; verify that the dev server forwards upgrade requests as intended before relying on `/api/v1/ws/{sessionId}` in local development.
- Avoid reading secret-bearing environment files. The inspected frontend does not need secrets for its current local rewrite.
