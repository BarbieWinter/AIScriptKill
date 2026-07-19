# 系统架构

## 架构意图

`/docs/ARCHITECTURE_OVERVIEW.md` 描述一个可复用 Script Engine 加载可插拔 Script Package：游戏规则属于引擎，故事、阶段、线索、角色、场景、媒体和 DM 指引属于 YAML/资产。`/doc/剧本系统设计.md` 补充产品边界：AI 可以在固定谜题内表演和控场，但不应改写凶手、动机或关键证据。

## 当前运行形态

当前单人 live 垂直切片已经打通 REST、YAML、LangGraph、checkpoint 和受控前端展示。MP-1 已加入
无网络双人状态机；MP-2 已集成 persistence/snapshot/auth/schema、room repository/service/routes 与 HTTP
lobby frontend，并通过应用层验证。真实 PostgreSQL/live-stack gates 仍未完成，因此 MP-2 不是 release-ready。

```text
Next.js web app
  -> /api/v1 REST
  -> FastAPI route/service/repository
  -> published package reconstruction
  -> LangGraph ScriptEngine + checkpoint saver + NPC/RAG
  -> session/chat/discovery projection
  -> Supabase/Postgres

WebSocket
  -> /api/v1/ws/{session_id}
  -> 仅未认证 ping/pong 心跳
```

真实后端入口是 `engine/api/main.py`。真实前端入口 `apps/web/app/page.tsx` 重定向到 `/library`；全应用 provider/layout 位于 `apps/web/app/layout.tsx`。

## 前端路由和运行模式

当前路由库存：

```text
/library
/library/[id]
/play/[sessionId]/select
/play/[sessionId]
/play/[sessionId]/review
/demo
/demo/live/[sessionId]
/demo/mock/[sessionId]
/multiplayer
/invite/[token]
/play/[sessionId]/lobby
```

两套玩法外壳要明确区分：

- `/demo/live/[sessionId]`：当前统一 live 验收路径。`LiveSessionClient` 调用真实 Session API，`GameSessionBoundary` 从七项资源 hydration，`DemoGameShell` 使用后端 presentation 的 YAML 场景/热点和真实 LangGraph 动作。
- `/demo/mock/[sessionId]`：使用同一个 `GameSessionBoundary` 和 `DemoGameShell`，仅替换成浏览器内 `MockSessionClient`；刷新会重置。
- `/demo`：视觉 demo 和会话启动器，可创建 live `snow-village`/`zhuosiyuan` 会话、恢复已有 UUID 或启动 mock。
- `/play/[sessionId]`：旧玩法页。它仍依赖全局 `isMockMode()`、`mockScenes`、直接 Mock engine/Mock WebSocket，并在 live 模式使用硬编码的 `back-alley` 热点；不能代表统一 live 数据边界。
- `/play/[sessionId]/select`：路由段在进入会话前仍语义上是 script 路径，但当前实现固定调用 `api.createSession("snow-village", "zhuosiyuan", "卓司元")`，再跳转后端返回的 session UUID，不再生成本地 session id。
- `/multiplayer`、`/invite/[token]`、`/play/[sessionId]/lobby`：MP-2 HTTP-only frontend。匿名 session
  bootstrap、current/create、invite accept、lobby polling 和 active placeholder 已实现；room backend 已接线。
  mocked-contract Playwright 的 1 passed 不是 live backend E2E。

`apps/web/lib/api.ts` 和 `apps/web/lib/ws.ts` 仍服务旧 `/play` 路径。统一 demo 使用 `apps/web/lib/game/types.ts`、`session-client.ts` 和 `components/game/GameSessionBoundary.tsx`，以 `source + sessionId` 隔离 store 和 client。

参见[前端架构](frontend.md)。

## FastAPI 路由库存

`/api/v1` 下当前暴露：

- Sessions：
  - `POST /sessions`
  - `GET /sessions/{session_id}`
  - `PATCH /sessions/{session_id}`，当前固定 409 `SESSION_RESTORE_UNAVAILABLE`
  - `GET /sessions/{session_id}/presentation`
  - `GET /sessions/{session_id}/clues`
  - `GET /sessions/{session_id}/evidences`
  - `POST /sessions/{session_id}/evidences/{evidence_id}/viewed`
  - `GET /sessions/{session_id}/character-chapters`
  - `GET /sessions/{session_id}/character-chapters/{chapter_id}`
  - `GET /sessions/{session_id}/characters`
  - `GET /sessions/{session_id}/chat-history`
  - `GET /sessions/{session_id}/cards`
  - `GET /sessions/{session_id}/review`
- MP-2 strict contract（已接线；真实数据库/live-stack gate 未运行）：
  - `GET /sessions/current`
  - `POST /sessions/{session_id}/invites`
  - `DELETE /sessions/{session_id}/invites/{invite_id}`
  - `POST /session-invites/{token}/accept`
  - `GET /sessions/{session_id}/snapshot`
  - `POST /sessions/{session_id}/commands`
- Actions：
  - `POST /sessions/{session_id}/actions`
  - `POST /sessions/{session_id}/final-submission`
- Packages：
  - `POST /packages`
  - `PATCH /packages/{package_id}`
  - `GET /packages`
  - `GET /packages/{package_id}`
- WebSocket：`/ws/{session_id}`，只有心跳。
- Health：`/health`、`/health/db`。

Legacy 认证依赖保持可选；包导入/状态变更要求管理员。MP-2 使用独立严格依赖，要求 verified Supabase
anonymous JWT、UUID `sub` 与 `is_anonymous=true`，再以 principal → membership 授权。Legacy
`player_id=NULL` 的“知道 UUID 可访问”行为不能用于多人房间。

参见[后端架构](backend.md)。

## 剧本包导入和运行期

剧本包导入路径：

```text
zip 或 package directory
  -> import_service.py
  -> package_loader.py 及 package_* 子模块
  -> strict YAML + strict character chapter Markdown frontmatter
  -> package_import_repository.py
  -> normalized script_* tables
```

运行期 action 路径：

```text
actions route
  -> session_service.perform_action
  -> runtime_session.LangGraphRuntimeActionExecutor
  -> per-session PostgreSQL advisory lock
  -> runtime_package_repository.get_runtime_package
  -> dedicated checkpoint AsyncSession
  -> ScriptEngine.from_package + RagRetriever + NPC responder
  -> restore latest graph checkpoint or bootstrap projection
  -> runtime_action_mappers/runtime_state_mappers
  -> game_sessions/chat_messages/session_discoveries projection
```

`engine/services/action_mappers.py` 中的旧固定动作不是生产 `/actions` 路径。当前 REST mapper 会编码热点、NPC、证物和推进 target，并返回真实状态差量和推进条件。

同会话写入由事务级 advisory lock 跨进程串行化，但锁连接、checkpoint saver 和请求投影各自提交，不是单一原子多人事务。`engine_message_id` 唯一索引和 discovery upsert 支持投影幂等；故障恢复仍需考虑 checkpoint 已提交、投影尚未提交的窗口。

## 展示和人物章节数据路径

### Presentation

`GET /sessions/{id}/presentation` 从已发布规范化包重建当前阶段和场景，只返回安全字段：

- 当前 stage id/name/actions/characters。
- scene id/name、公开 description、ambient color 和浏览器安全背景 URL。
- 包内有序 public hotspots 的 id/label/坐标/尺寸。
- 可选 judgment question 和有序 options。

它不返回 hotspot `on_click`、私有/DM-only 热点或 `correct_option`。点击后由客户端提交 `examine_scene`，规则仍在服务端 YAML/StateGraph 执行。

### Character chapters

```text
character_scripts/*.md
  -> strict frontmatter import
  -> script_character_chapters
  -> game_start 或 unlock_character_chapter 事件
  -> session_discoveries unlocked/viewed
  -> 按 player_character_id + session discovery 授权 list/read
```

章节正文不自动进入普通 `script_knowledge` RAG 索引。章节 API 和 NPC RAG 是两个独立授权面。

## 数据平台

`supabase/migrations/` 包含：

- 基础剧本包、运行时、向量、RLS、索引、权限和 schema 注释迁移。
- FastAPI data-access boundary，撤销 anon/authenticated 直接表权限。
- checkpoint idempotency 和 pending writes。
- `script_character_chapters` 与 character-chapter discovery 支持。
- `text-embedding-v4` 使用的 1024 维 `script_knowledge.embedding`。
- `chat_messages.engine_message_id` 投影幂等约束。
- MP-2 mode-aware `game_sessions` 扩展，以及 members、assignments、invites、required members、principal
  reservations 五张 service-role-only 表。

`script_knowledge` 不是“未来 RAG”占位表。当前已实现 package chunking/indexing、deterministic/DashScope embedding provider、vector + BM25 候选、rerank、阶段/角色/已解锁线索权限过滤和 provider factory。

`supabase/seed/dev_seed.sql` 仍是旧 Phase 1 数据和 1536 维向量，和当前 1024 维 schema、`script-packages/snow-village` YAML 内容不一致。它不能作为当前 live 垂直切片的权威内容。

## AI、RAG、媒体和 LangGraph

已实现并进入生产单人 action 路径的部分：

- LangGraph StateGraph、条件 DSL、事件总线和 PostgreSQL checkpoint saver。
- REST action -> runtime mapper -> StateGraph -> projection。
- `RagRetriever` 和授权检索。
- OpenAI-compatible NPC 生成；配置不完整、provider/RAG 失败或输出过滤失败时使用确定性 fallback。

仍未形成公开运行时入口的部分：

- AI-DM、Guard、Hint 的完整产品编排。
- WebSocket gameplay events/replay/presence/resync。
- MP-2 真实数据库/live-stack gates、后续 revision event/outbox 和完整多人 gameplay。
- 媒体签名 URL/代理下载与完整 orchestrator。

`MULTIPLAYER_V1` 是 MP-2 fail-closed gate；`ROOM_EVENTS_V1` 和 `AI_DM_V1` 仍没有运行时消费方。即使
打开 multiplayer flag，也不能替代尚未完成的真实数据库和 live-stack 验收。

## 重要横切约束

- 防剧透：浏览器无表权限；FastAPI 根据 stage、character、discovery 和白名单字段做投影，RLS 提供纵深防御。
- 权威内容：当前单人 vertical slice 以可导入 `script-packages/snow-village` YAML/Markdown 为准；Mock 仅供 UI 预览。
- 权威状态：live action 以最新 LangGraph checkpoint 为首选，有限 session JSONB 是查询投影和无 checkpoint 时的 bootstrap。
- 事务边界：checkpoint 和投影不是一个原子提交，不能套用尚未实现的多人 event/outbox 原子性描述。
- WebSocket 心跳不是多人事件通道。
