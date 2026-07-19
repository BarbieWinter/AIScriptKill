# 前端架构

## 技术栈和应用外壳

前端位于 `apps/web`。`apps/web/package.json` 定义了一个 Next.js 15、React 19、TypeScript 应用，并使用 Zustand、TanStack Query、framer-motion、Howler、Konva/react-konva、sonner、lucide-react 和 Tailwind 相关工具。

`apps/web/app/layout.tsx` 使用 TanStack Query provider 包裹应用，并加载来自 `apps/web/app/globals.css` 的全局样式。`apps/web/app/page.tsx` 会把访问者重定向到 `/library`。

设计意图见 `/docs/FRONTEND_EXPERIENCE_DESIGN.md` 和 `/docs/SONNET5_HANDOFF.md`：应用应该像沉浸式互动电影，使用场景背景、克制的覆盖层、音频/动画反馈和围绕谜题的流程，而不是通用聊天 UI。

## 路由图

当前页面还包括 MP-2 HTTP lobby 基础：

- `/multiplayer`：复用/建立 Supabase anonymous session，查询 nullable current room，创建或恢复
  `mp1-two-player` lobby。
- `/invite/[token]`：只提交一次 invite accept；成功后 `router.replace()` 到 lobby，避免 token 保留在
  active URL/history。
- `/play/[sessionId]/lobby`：React Query 读取安全 snapshot，仅在 `lobby` 每 2 秒 polling；`active` 停止
  polling 并显示 MP-6 placeholder。

Legacy/单人页面：

- `/library`：`apps/web/app/library/page.tsx`。展示硬编码的雪村剧本库体验，而不是查询真实剧本包。
- `/library/[id]`：`apps/web/app/library/[id]/page.tsx`。调用 `api.getPackage(scriptId)`，并用 Mock 角色预览渲染详情；live 模式依赖后端 `GET /packages/{id}`。
- `/play/[sessionId]/select`：`apps/web/app/play/[sessionId]/select/page.tsx`。路由段名是 `sessionId`，但页面实际把它当作 script id，并在选角后创建本地 `session-{Date.now()}` 路由。
- `/play/[sessionId]`：`apps/web/app/play/[sessionId]/page.tsx`。主玩法屏幕。live 模式从后端读取 session 并连接真实 WebSocket 心跳；Mock 模式仍使用 `getMockEngine`、`mockScenes` 和 `MockWsClient`。
- `/play/[sessionId]/review`：`apps/web/app/play/[sessionId]/review/page.tsx`。调用 `api.getReview(sessionId)`，渲染分数、正确性、遗漏线索、线索覆盖率、玩家路径和动作。

设计文档中的预期产品流程是：

```text
/library -> /library/{script_id} -> /play/{script_id}/select -> /play/{session_id} -> /play/{session_id}/review
```

## 状态管理

`apps/web/stores/gameStore.ts` 是玩法 UI 状态的共享 Zustand store。它跟踪：

- 会话身份：`sessionId`、`scriptId`、`playerCharacterId`。
- 进度：`currentStage`、`currentScene`、可用动作、角色、场景。
- 玩家发现：已解锁线索、已发现证据、卡牌。
- 聊天状态：消息和输入指示器。
- 媒体状态：当前 BGM 和播放标志。
- UI 状态：活跃面板、选中的热点、转场。

该 store 只在内存中。刷新页面会丢失状态，除非 Mock 引擎或后端重新加载路径能重建它。

## API 和 WebSocket 边界

`apps/web/lib/api.ts` 是真实/Mock REST 客户端。它的方法覆盖会话创建/获取/更新、动作、最终提交、线索、证据、角色、聊天历史、卡牌、复盘、剧本包列表和剧本包详情。在浏览器中，除非 `NEXT_PUBLIC_USE_MOCK === "false"`，否则默认启用 Mock 模式。

`apps/web/lib/ws.ts` 是真实 WebSocket 客户端。它优先使用 `NEXT_PUBLIC_WS_URL`，否则连接同一浏览器 host 下的 `/api/v1/ws/{sessionId}`，按 `message.type` 分发事件，自动重连，并每 30 秒发送一次 `session.ping`。

`apps/web/lib/mock-ws.ts` 为 Mock 模式模拟更丰富的玩法事件。后端 WebSocket 目前只接受 `session.ping` 并发出 `session.pong`，所以不要期待真实服务端事件已经与 Mock 对齐。

### MP-2 lobby client boundary

`apps/web/lib/auth/anonymous-session.ts` 复用有效 Supabase session、按需 refresh，只在没有 session 时
`signInAnonymously()`，并去重并发 bootstrap。`apps/web/lib/multiplayer/room-client.ts` 为 MP-2 请求附加
bearer token；legacy API client 不变。

大厅只允许本人 assign/unassign 与 ready/unready。host 可创建、复制和撤销 15 分钟邀请并 start；本地
start 按钮要求房间满员、角色完整且互异、全员 ready 且服务端 `can_start=true`。revision mismatch
只 invalidates snapshot，不自动重放 mutation。大厅不挂载 legacy gameplay store，也不建立 application
WebSocket。

`apps/web/e2e/multiplayer-lobby.spec.ts` 使用三个独立 browser contexts，但 Supabase Auth 和全部 room HTTP
均由测试内存 mock。它的 1 passed 是 mocked-contract browser evidence，不是 real Supabase/FastAPI/
PostgreSQL E2E。后端 room repository/service/routes 已接线并通过应用层验证，但真实 live-stack gate 尚未运行。

## 玩法 UI 组成

主玩法页大致按这些层组织体验：

- 通过 `SceneBackground` 实现全屏背景。
- 通过 `SceneHotspots` 实现场景热点交互。
- 顶部动作/导航栏。
- 通过 `ChatPanel` 实现底部聊天/视觉小说面板。
- `ClueBoard`、`EvidenceBackpack`、`FinalSubmission` 和 `TruthReveal` 的 modal 或 sheet 式覆盖层。
- `StageTransition`、闪光/紧张感视觉效果和 toast 反馈。

多个组件会直接调用 Mock 引擎，包括 `ChatPanel`、`SceneHotspots`、`EvidenceBackpack` 和 `FinalSubmission`。因此当前玩法界面对 UX 迭代有用，但还不能代表完整真实后端玩法事件集成。

## Mock 数据领域

`apps/web/lib/mock-data.ts` 包含一套较完整的雪村场景：剧本包元数据、角色、阶段、场景、热点、线索、证据、对话反应、阶段推进、最终评分和复盘生成。它目前是仓库中最完整的可执行游戏内容。

有一个已知内容不一致：Mock 最终评分把 `chengjun` 视为正确，而游戏页的真相揭示文案称 `wangdada` 是真正凶手。把 Mock 内容当作规范剧本包数据之前，需要先解决这个问题。

## 变更指引

修改剧本库、详情或复盘页面时，明确页面应该继续保持 Mock 友好，还是通过 `apps/web/lib/api.ts` 转为真实优先。

修改主玩法时，明确集成目标：

- 仅 Mock UX：更新 `mock-data.ts`、`mock-ws.ts` 和直接组件调用。
- 真实集成：通过 `api.performAction` 或 `WsClient` 路由动作，用真实响应更新 store，并考虑后端当前有限的动作和 WebSocket 行为。
- 产品路由正确性：考虑重命名或重构 `/play/[sessionId]/select`，因为它在会话存在前接收的是 script id。

添加视觉功能时，应对齐 `/docs/FRONTEND_EXPERIENCE_DESIGN.md` 和现有组件风格，而不是创建另一套设计语言。
