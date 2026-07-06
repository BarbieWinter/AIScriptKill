# 后端架构

## 入口和中间件

后端入口是 `engine/api/main.py`。`create_app()` 会构建 FastAPI 应用，并安装：

- 来自 `engine/api/errors.py` 的自定义 `ApiError` 和数据库异常处理器。
- 来自 `engine/api/middleware/rate_limit.py` 的按客户端内存限流。
- 来自 `engine/api/config.py` 的 CORS origins。
- 来自 `engine/api/routes/sessions.py`、`actions.py`、`packages.py` 和 `engine/api/websocket/handler.py` 的路由。
- `/health` 和 `/health/db` 端点。

`/health/db` 调用 `engine/db/session.py::check_database_connection()`，验证连接以及必要 public 表是否存在，包括向量迁移中的 `script_knowledge`。

## 配置

`engine/api/config.py` 使用 Pydantic settings，预期 Supabase/database 环境变量包括 `SUPABASE_URL`、`SUPABASE_PUBLISHABLE_KEY`、`SUPABASE_SECRET_KEY`、`DATABASE_URL`、可选的 `DATABASE_POOLER_URL`、`CORS_ORIGINS` 和 `RATE_LIMIT_PER_MINUTE`。

当前重要注意点：settings 读取项目根目录 `.env` 和系统环境变量；`.env.example` 只保留占位符。真实运行配置应通过本地 `.env` 或部署环境提供。

数据库连接在存在 `DATABASE_POOLER_URL` 时优先使用它，否则使用 `DATABASE_URL`。普通 `postgresql://` URL 会转换为 `postgresql+asyncpg://`；本地数据库不强制 SSL，远程连接使用 `ssl=require`。

## 认证和授权

`engine/api/middleware/auth.py` 定义了跨路由使用的依赖：

- 无 bearer token：返回 `CurrentUser(subject="anonymous", role="anonymous")`。
- 有 bearer token：根据项目 JWKS 校验 Supabase JWT，并返回认证用户。
- 剧本包导入和剧本包状态更新使用仅管理员可访问的依赖。后端只信任 Supabase `app_metadata.role` / `app_metadata.roles` 做这个判断；浏览器传来的 user metadata 不用于授权。

会话访问由 `engine/services/session_service.py` 强制执行。如果 `game_sessions.player_id` 为 `NULL`，任何知道会话 UUID 的人都能访问。如果设置了 `player_id`，它必须匹配已认证的 Supabase user id。

数据库级 RLS 策略位于 `supabase/migrations/004_rls_policies.sql`，但扩展授权时仍需考虑后端服务端访问模式和 service role 使用方式。

## API 路由

### Sessions

`engine/api/routes/sessions.py` 暴露：

- `POST /api/v1/sessions`：基于已发布剧本包和偏好角色创建会话。
- `GET /api/v1/sessions/{session_id}`：返回当前会话状态摘要。
- `PATCH /api/v1/sessions/{session_id}`：恢复检查点。
- `GET /api/v1/sessions/{session_id}/clues`：已解锁线索。
- `GET /api/v1/sessions/{session_id}/evidences`：已发现证据。
- `GET /api/v1/sessions/{session_id}/characters`：当前可用角色。
- `GET /api/v1/sessions/{session_id}/chat-history`：已存储聊天历史。
- `GET /api/v1/sessions/{session_id}/cards`：可用卡牌，来自带卡牌类型的 evidence 行。
- `GET /api/v1/sessions/{session_id}/review`：已完成复盘。

### Actions

`engine/api/routes/actions.py` 暴露：

- `POST /api/v1/sessions/{session_id}/actions`
- `POST /api/v1/sessions/{session_id}/final-submission`

当前动作处理器在 `engine/services/action_mappers.py` 中映射 action type。它是确定性的占位逻辑，不是 AI 驱动，也还没有完全由剧本包驱动。

### Packages

`engine/api/routes/packages.py` 暴露：

- `POST /api/v1/packages`：上传并导入 zip 归档。可选 `publish=true` 会在导入时发布。
- `PATCH /api/v1/packages/{package_id}`：更新剧本包状态。
- `GET /api/v1/packages`：为前端剧本库列出已发布剧本包。

前两个剧本包端点是后端管理员操作。前端客户端必须调用 FastAPI API，并提供管理员 Supabase Auth JWT；不能直接写 Supabase 表。

剧本包导入会在 upsert package 记录后，替换该 script id 的全部结构行。

### WebSocket

`engine/api/websocket/handler.py` 接受 `/api/v1/ws/{session_id}`，目前只支持心跳：接收 `session.ping`，发送带 session id 的 `session.pong`。它还不会流式推送玩法事件。

## 服务层和仓储层

后端遵循 route -> service -> repository 分层。

`engine/services/session_service.py` 协调会话生命周期、动作执行、最终提交和数据查询。持久化委托给 `engine/repositories/session_repository.py`，再由它委托给聚焦模块：

- `session_seed.py`：根据已发布剧本包、入口阶段、可玩角色和阶段定义默认值派生初始运行期状态。
- `session_mutations.py`：创建会话/检查点、恢复检查点、应用动作效果、upsert 发现记录、保存提交/复盘。
- `session_queries.py`：加载会话、阶段、发现、角色、聊天、卡牌、复盘。
- `session_context.py`：在可见性敏感查询前设置 `app.current_stage` 和 `app.player_character` 等 Postgres setting。
- `session_models.py` 和 `session_rows.py`：运行期状态和行映射。

`engine/services/import_service.py` 通过 `engine/core/package_loader.py` 校验上传的剧本包 zip，并通过 `engine/repositories/package_import_repository.py` 写入。

`engine/services/package_service.py` 通过剧本包仓储列出和更新剧本包状态。

## 当前玩法行为

当前 `action_mappers.py` 行为有意保持简单：

- `talk_to_npc`：返回固定的王大大风格回复，并持久化玩家/NPC 聊天消息。
- `examine_scene`：发现固定线索 `broken_glass`，更新已解锁线索/当前场景，并持久化一条发现记录。
- `show_evidence` 和 `use_card`：返回固定响应，没有有意义的状态变更。
- `request_advance`：总是从 `act1_investigation` 转到 `act1_event`，并带固定 actions。
- `open_clue_board`：返回 `advance_denied`，说明前端应打开本地视图并调用线索端点。
- 最终提交：分数为 `min(100, 55 + 10 * len(key_evidences))`，`correct=True`，并使用固定 missed evidence ids 和 ending id。

不要把这些当作最终业务逻辑。

## 骨架区域

文档和依赖提到了 LangGraph、agents、RAG、媒体编排、条件 DSL 和评分。当前实现主要在这些位置仍是骨架：

- `engine/agents/`
- `engine/rag/`
- `engine/media/orchestrator.py`
- `engine/core/script_engine.py`
- `engine/core/condition_evaluator.py`
- `engine/core/event_bus.py`
- `engine/core/checkpoint.py`
- `engine/services/scoring_service.py`

未来工作应通过现有 service/repository 边界集成这些功能，而不是绕过持久化和授权。
