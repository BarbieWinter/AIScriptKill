# 前端架构

```text
┌─ OPENWIKI PAGE ──────────────────────────────────────────────────────────────┐
│ KIND      reference                                                          │
│ SCOPE     Next.js routes, clients, stores, Mock and multiplayer lobby        │
│ VERIFIED  2026-07-23 @ WORKTREE                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

[Home](../quickstart.md) / [Architecture](system.md) / **Frontend**

前端位于 `apps/web`，使用 Next.js 15、React 19、TypeScript、TanStack Query
和 Zustand。

## 一览

- [LIVE] **选角流程** — 动态加载角色并调用 `api.createSession()`。
- [LIVE] **单人 Live shell** — 读取真实 Session API 和 presentation。
- [MOCK] **单人 Mock shell** — 使用同一游戏外壳和浏览器内 client。
- [LIVE] **多人大厅** — 匿名身份、邀请、选角、准备和启动。
- [LIVE] **多人 gameplay** — active/completed 房间使用 HTTP polling 可完整通关。
- [LEGACY] **demo routes** — `/demo/*` 只重定向到当前 `/play/*` 路由。

## 路由

```text
/
  -> /library

/library
  -> /library/{scriptId}
  -> /play/{scriptId}/select
  -> /play/{scriptId}/{gameSessionId}
  -> /play/{scriptId}/review

/multiplayer
  -> /invite/{token}
  -> /play/{roomSessionId}/lobby
```

选角页的目录名仍是 `[sessionId]`，但该段在创建会话前表示 `scriptId`。页面会：

1. 调用 `api.getPlayableCharacters(scriptId)`；
2. 调用 `api.createSession(scriptId, characterId, characterName)`；
3. 跳转到 `/play/{scriptId}/{gameSessionId}`。

[CAUTION] 不要再使用已删除的 `apps/web/app/play/[sessionId]/page.tsx` 作为
当前 gameplay 入口。

## Client 与状态

### 单人

`apps/web/lib/api.ts` 仍提供全局 Mock/Live API wrapper：

```text
NEXT_PUBLIC_USE_MOCK != "false"  -> Mock
NEXT_PUBLIC_USE_MOCK == "false"  -> Live
```

`GameSessionBoundary` 根据 `source + sessionId` 创建 client/runtime，并把服务端资源
装载到会话级 Zustand store。`DemoGameShell` 负责场景、面板和互动展示。

`make dev` 与 `make dev-web` 默认显式使用 Mock；Live 联调需执行：

```bash
NEXT_PUBLIC_USE_MOCK=false make dev
```

### 多人房间与 gameplay

`apps/web/lib/auth/anonymous-session.ts` 建立或刷新 Supabase anonymous session。
`apps/web/lib/multiplayer/room-client.ts` 为请求附加 bearer token，并提供 current、
create、invite、联合 snapshot、完整 room command 和 completed review 方法。

`LobbyBoundary` 在 `lobby`、`active` 与 `completed` 状态每 2 秒 polling；completed 仍需刷新同伴的展示位置，只有 presence 写入会在 completed 停止。
首次读取失败显示阻塞错误；已有缓存时的轮询中断保留当前页面并显示可重试提示。它按
`status` discriminated union 分派：

```text
lobby                 -> LobbyShell
active / completed    -> MultiplayerMansionShell
```

`MultiplayerMansionShell` 复用 `MansionDemo` 的本地移动、碰撞、镜头与近距离交互，但不把
多人快照写入单人 Zustand store。角色章、公开档案、协作提示、讨论室、圆桌判断与 completed-only
复盘由 participant-safe snapshot 映射成固定玩法入口、可选阶段热点和覆盖面板；公开材料与
协作提示无需接近热点即可打开，多人模式也不加载 `demoArticles` 等静态故事 fixture。提示仅在
讨论阶段允许按级请求和全员确认，只渲染 snapshot 已揭示正文，进入正式判断后自动关闭。两个角色分别
映射到不同 outfit/accessory/palette；本地 pose 约每 500ms
合并为一次 authenticated HTTP PUT，服务端只保存该成员的最新展示位置，另一端从 2 秒快照
polling 中渲染真实同伴。坐标不进入 `GameStateV2`、revision 或 event，不能成为剧情或物理权威。
失败的讨论发送保留草稿；复盘可重试；网络结果不确定时，client 复用同一 `command_id` 重试一次；
revision mismatch 只刷新，不自动重放 stale intent。

当前 audited tree 只有 `MultiplayerMansionShell` 承担 active/completed gameplay 产品入口，不存在第二套已接线 gameplay shell。

## UI 所有权

| 区域 | 状态所有者 | 数据来源 |
|---|---|---|
| 单人 Live | `GameSessionRuntime` | FastAPI Session API |
| 单人 Mock | `MockSessionClient` | `mock-data.ts` |
| 多人房间 | TanStack Query | room/gameplay HTTP API |
| 多人 completed review | TanStack Query | member-only review API |

[CAUTION] `mock-data.ts` 是 UI fixture，不是 authored package。修改 Mock 故事不能
替代修改 `script-packages/`。

## 浏览器验证

- Route-mocked Playwright 覆盖大厅启动、真实键盘移动、不同角色外观，以及双 browser context 中双向位置可见。
- `multiplayer-gameplay.spec.ts` 的 mock 会把每个 JWT identity 的 PUT pose 写入 latest-value store，
  再通过另一端的 snapshot polling 验证 host→guest 与 guest→host 坐标变化；同时验证 presence body
  不含 `member_id` 或 `character_id`，两位玩家仍只收到自己的 participant-safe 章节，并可在不移动时
  通过固定入口打开公开材料与协作提示。测试还覆盖提示请求、另一位玩家确认、刷新恢复，以及进入正式判断后关闭提示入口。
- `multiplayer-lobby.spec.ts` 验证房间启动后进入 `MansionDemo`、键盘移动有效且没有 gameplay WebSocket。
- `multiplayer-lobby.live.spec.ts` 是无 Mock 的真实 anonymous identity 技术闭环；真实 PostgreSQL/API
  环境应用最新迁移后，应再次执行场景定位器与双向移动回归。
- Slim M2/M3 浏览器闭环刻意不使用 gameplay WebSocket。

## 边界

- **包含：** 页面路由、client、store、polling 和 UI 数据所有权。
- **不包含：** 后端 reducer、数据库迁移和完整视觉设计规格。
- [SECURITY] **身份** — 邀请 token 不应保留在成功后的 active URL/history。
- [CAUTION] **WebSocket** — 单人 client 的心跳不提供多人 gameplay events。

## 变更导航

| 修改目标 | 首先查看 | 验证入口 |
|---|---|---|
| 路由流程 | `apps/web/app/` | `npm --prefix apps/web run build` |
| 单人 client | `lib/game/session-client.ts` | legacy recovery spec |
| 多人房间/gameplay | `components/multiplayer/` | lobby + gameplay specs |
| 真实双人通关 | `multiplayer-lobby.live.spec.ts` | `make test-mp2-live` |
| Mock 内容 | `lib/mock-data.ts` | Mock 页面手工/浏览器测试 |
| 启动模式 | `Makefile`, `lib/api.ts` | `make -n dev-web` |

## 权威来源

- **路由：** `apps/web/app/`。
- **单人运行时：** `apps/web/lib/game/`, `apps/web/components/demo/`。
- **多人大厅：** `apps/web/lib/multiplayer/`, `components/multiplayer/`。
- **设计：** `docs/FRONTEND_EXPERIENCE_DESIGN.md` 只描述总体体验意图。

---

[Previous: Backend](backend.md) · [Home](../quickstart.md) ·
[Next: Gameplay](../domain/script-gameplay.md)
