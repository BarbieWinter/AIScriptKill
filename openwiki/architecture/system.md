# 系统架构

## 架构意图

预期架构记录在 `/docs/ARCHITECTURE_OVERVIEW.md`：一个可复用的 Script Engine 加载可插拔的 Script Package。游戏逻辑属于引擎；故事内容、阶段规则、线索、角色、场景、媒体和 DM 指引属于剧本包 YAML/资产。`/doc/剧本系统设计.md` 补充了产品边界：AI 在固定谜题内表演和控场，但不应改写凶手、动机或关键证据。

## 当前运行形态

当前源码只是目标架构的部分实现。

```text
Next.js web app
  -> REST /api/v1 和 WebSocket 契约封装
  -> FastAPI backend
  -> service layer
  -> repository layer
  -> Supabase/Postgres tables and RLS

前端主玩法路径
  -> live 模式读取真实 session 并连接 WebSocket 心跳
  -> 具体玩法交互仍大量依赖 mock data
```

真实后端入口是 `engine/api/main.py`。它创建 FastAPI 应用，安装自定义 API/数据库错误处理、限流、CORS、会话/动作/剧本包路由、WebSocket 路由，以及 `/health` 和 `/health/db`。

真实前端入口是 `apps/web/app/page.tsx`，会重定向到 `/library`。全应用 provider 和 layout 位于 `apps/web/app/layout.tsx`。

## 主要组件

### 前端

`apps/web` 是一个 Next.js App Router 应用，使用 TypeScript、React 19、Zustand、TanStack Query、framer-motion、Howler、Konva/react-konva、lucide-react 和 Tailwind。产品路由流是：

```text
/library
/library/[id]
/play/[sessionId]/select
/play/[sessionId]
/play/[sessionId]/review
```

`apps/web/lib/api.ts` 中的 API wrapper 对齐文档化的 `/api/v1` 契约，并支持 Mock 模式。`apps/web/lib/ws.ts` 中的 WebSocket wrapper 连接 `/api/v1/ws/{sessionId}`，并定期发送 `session.ping`。主玩法页面在 live 模式会使用真实 session 状态和 WebSocket 心跳，但场景、热点和复杂玩法反馈仍主要来自 Mock 数据。

参见[前端架构](frontend.md)。

### FastAPI 网关

后端在 `/api/v1` 下暴露这些路由组：

- `/sessions`：创建/获取/恢复会话，并查询线索、证据、角色、聊天历史、卡牌和复盘。
- `/sessions/{session_id}/actions`：执行玩法动作。
- `/sessions/{session_id}/final-submission`：提交最终推理并持久化复盘记录。
- `/packages`：导入 zip 剧本包归档、更新剧本包状态、列出和读取已发布剧本包。
- `/ws/{session_id}`：目前只有心跳的 WebSocket 骨架。

在 API 依赖层，认证是可选的。没有 bearer token 时，`engine/api/middleware/auth.py` 返回匿名用户；有 token 时会校验 Supabase JWT。

参见[后端架构](backend.md)。

### 剧本包和运行期服务

剧本包导入实现为：

```text
UploadFile zip
  -> engine/services/import_service.py
  -> engine/core/package_loader.py
  -> engine/core/package_schema.py 中的 Pydantic YAML 模型
  -> engine/repositories/package_import_repository.py
  -> script_* 结构表
```

会话运行期实现为：

```text
route
  -> engine/services/session_service.py
  -> engine/repositories/session_repository.py
  -> 聚焦的 session_* repository 模块
  -> game_sessions.state JSONB、checkpoints、chat、discoveries、submissions、reviews
```

`engine/services/action_mappers.py` 目前是确定性的玩法占位逻辑。它返回固定 NPC 回复、场景发现、阶段转换 patch 和最终评分。

### 数据平台

Supabase/Postgres schema 位于 `supabase/migrations/`：

- `001_script_tables.sql`：剧本包、阶段、角色、线索、证据、场景和媒体表。
- `002_runtime_tables.sql`：游戏会话、检查点、聊天消息、发现记录、最终提交和复盘。
- `003_vector_tables.sql`：未来 RAG 使用的 `script_knowledge` pgvector 表。
- `004_rls_policies.sql`：service role、认证玩家访问、阶段/角色可见性的 RLS 策略。
- `005_runtime_persistence_indexes.sql`：会话、剧本包、提交、复盘、检查点、卡牌/证据查询索引。
- `006_api_role_privileges.sql`：授权和公开已发布剧本包策略。

`engine/db/session.py` 创建异步 SQLAlchemy engine，优先使用 `DATABASE_POOLER_URL`，其次使用 `DATABASE_URL`，并要求 SSL。

### AI、RAG、媒体和 LangGraph

仓库命名和文档指向 LangGraph、DM/NPC/Guard/Hint agent、RAG 检索和媒体编排。当前源码尚未把这些接入玩法。代表性的骨架文件包括 `engine/agents/*.py`、`engine/rag/*.py`、`engine/media/orchestrator.py`、`engine/core/script_engine.py`、`engine/core/condition_evaluator.py` 和 `engine/services/scoring_service.py`。

添加这些功能时，不要假设文档化架构已经生效。应从真实 route/service/repository 流程出发，谨慎引入集成点。

## 重要横切约束

- 防剧透是核心产品要求。RLS 策略和 `stage_visible`、`visibility`、`character_id` 等剧本包元数据字段用于防止过早泄露，但应用层行为仍不完整。
- 后端目前允许 `player_id = NULL` 的匿名会话；只要知道 UUID，`session_service._assert_session_access` 就允许访问这些会话。
- 前端和后端都知道 API 契约，但活跃玩法仍然以 Mock 为先。
- 现有文档可能描述的是预期验收标准，而不是当前行为。发生冲突时以源码为准。
