# 后端架构

## 入口和中间件

后端入口是 `engine/api/main.py`。`create_app()` 会构建 FastAPI 应用，并安装：

- 来自 `engine/api/errors.py` 的自定义 `ApiError` 和数据库异常处理器。
- 来自 `engine/api/middleware/body_limit.py` 的累计 ASGI 请求体限制：普通请求 1 MiB，
  剧本包 multipart 信封 65 MiB；chunked 请求同样受限。
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
- 有 bearer token：根据项目 JWKS 校验 Supabase JWT 的签名、issuer、audience、有效期和
  `aud`/`exp`/`iss`/`sub` 必需 claims，并返回认证用户。
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

`engine/api/websocket/handler.py` 接受 `/api/v1/ws/{session_id}`，其中 `session_id` 必须是 UUID；非法 path 值会在 handler 接受连接前被 FastAPI 关闭。目前只支持心跳：接收 JSON 文本 `session.ping`，发送带字符串 session id 的 `session.pong`，binary 帧以 1003 关闭。连接管理器限制全局 100 条、单客户端 4 条连接；Uvicorn 在 ASGI 前限制单帧 64 KiB、接收队列 4 条，应用层继续执行同等消息上限、每分钟最多 30 条和 60 秒空闲关闭。该端点尚未定义 JWT 通过 query、cookie 或 subprotocol 传输的契约，也不会流式推送玩法事件；完整认证绑定和事件流统一延后到 T-2.6 API-引擎接线阶段。

## 服务层和仓储层

后端遵循 route -> service -> repository 分层。

`engine/services/session_service.py` 协调会话生命周期、动作执行、最终提交和数据查询。持久化委托给 `engine/repositories/session_repository.py`，再由它委托给聚焦模块：

- `session_seed.py`：根据已发布剧本包、入口阶段、可玩角色和阶段定义默认值派生初始运行期状态。
- `session_mutations.py`：创建会话/检查点、恢复检查点、应用动作效果、upsert 发现记录、保存提交/复盘。
- `session_queries.py`：加载会话、阶段、发现、角色、聊天、卡牌、复盘。
- `session_context.py`：在可见性敏感查询前设置 `app.current_stage` 和 `app.player_character` 等 Postgres setting。
- `session_models.py` 和 `session_rows.py`：运行期状态和行映射。

`engine/services/import_service.py` 通过 `engine/core/package_loader.py` 校验上传的剧本包 zip，并通过 `engine/repositories/package_import_repository.py` 写入。剧本包加载器近期已拆分为几个职责明确的模块：

- `package_archive.py`：zip 可见文件过滤、`package.yml` 定位、YAML 读取和 JSONB 值归一化。
- `package_directory.py`：把松散剧本包目录打包为内存 zip，供 `load_package_directory()` 复用同一套加载流程。
- `package_yaml.py` 及按内容拆分的 `package_*_yaml.py`：Pydantic YAML 输入模型，使用
  strict 类型和 `extra="forbid"` 拒绝未知建模字段。
- `package_records.py`：把 YAML 定义转换为 `PackageRecord`、`StageRecord`、`CharacterRecord`、`ClueRecord`、`EvidenceRecord`、`SceneRecord`、`MediaRecord` 和 `EndingRecord`。
- `package_content_loader.py`：读取角色、线索、证据、场景、媒体、`endings.yml`、`dm_guide/*.yml` 和 `assets/`，并把 `dm_guide` 排除在公开 `script_packages.config` 之外。
- `package_importer.py` 和 `package_storage.py`：可选上传 `assets/` 到强制私有的 Supabase
  Storage bucket，并把剧本包 YAML 中匹配的本地素材路径重写为 `storage://` 定位符；
  面向客户端的签名 URL/代理下载属于 T-2.6。
- `package_validation.py`、`package_reference_validation.py`、`package_event_validation.py`、`package_asset_validation.py` 和 `package_validation_context.py`：校验 package id、重复 id、跨文件引用、条件/事件引用、本地资产路径，并返回角色阶段知识缺失 warnings。

`engine/core/package_schema.py` 现在主要保存导入记录 dataclass，而不是完整 YAML schema。`ScriptPackageImport` 包含导入记录集合、`stage_index`、`dm_guide`、`assets` 和 `warnings`。仓储层会写入公开结构表、`script_endings` 和仅 service-role 可访问的 `script_dm_guides`；重复导入会先删除旧结构再重建。

`engine/services/package_service.py` 通过剧本包仓储列出和更新剧本包状态。

条件 DSL evaluator 现在位于 `engine/core/condition_evaluator.py` 及其拆分模块：`condition_models.py` 解析条件树，`condition_state.py` 调度叶子求值并生成缓存快照，`condition_leaf_evaluators.py`/`condition_leaf_helpers.py` 读取 `GameState` 中的阶段、线索、证据、对话、玩家行为、时间、提交答案、事件和全局计数状态，`condition_trace.py` 输出调试 trace。`evaluate_condition()` 会按条件树和相关 `GameState` 片段生成缓存键；`evaluate_condition_with_trace()` 绕过布尔缓存返回完整遍历树；`ConditionEvaluationOptions.force_conditions` 可在测试/调试中强制某类条件恒真或恒假。

通用玩法引擎现在位于 `engine/core/script_engine.py`：它用 LangGraph `StateGraph` 组装 `stage_entry`、`player_action`、`npc_response`、`check_conditions`、`process_events`、`stage_exit` 和 `ending` 节点，并通过 `_route_action`、`_should_transition` 条件边控制分支。每次 `run_action()` 会从可注入的 `Clock` 推进 `current_time`；首次进入阶段时，同一时刻会写入 `stage_entered_at`，阶段切换后重置计时起点。系统默认使用 UTC 时钟，测试可以注入固定时钟。

核心动作会先按当前阶段校验 `available_actions` 和 target，再写入状态：NPC 必须属于 `available_characters`，场景必须属于 `available_scenes`，出示证物使用 `evidence_id:character_id` 且证物已发现、角色当前可用，卡牌 id 不得为空，线索板动作不得携带 target。禁用动作和非法 target 会抛出带稳定 `code` 的 `ScriptEngineActionError`，不会再静默成为 no-op。这里的复合 target 是 core 边界；T-2.6 的 API mapper 负责从 REST 多字段请求编码它。

`engine/core/event_bus.py` 执行 `dm_narrate`、`play_audio`、`unlock_*`、`npc_*`、`transition_to` 等剧本事件。线索发现 hook 使用与阶段退出相同的 `evaluate_condition()` 评估完整条件树；未知运行时事件会在调用外部 sink 前以 `EventActionError` 失败。`script_runtime.py` 维护阶段顺序和不可跳跃/不可回退约束。

`checkpoint.py` 提供 LangGraph async checkpointer。checkpoint 以唯一 `(session_id, thread_ts)`
upsert 到 `session_checkpoints`；pending writes 独立写入 `session_checkpoint_writes`，主键为
`(session_id, checkpoint_id, task_id, write_idx)`，因此 write-before-checkpoint、不同 saver
进程和重试都不会互相覆盖。每个 `aput`、`aput_writes` 和 `adelete_thread` 都会自行提交，
所以 saver 必须接收专用 `AsyncSession`，不能与 FastAPI 请求事务共享。读取时会兼容合并
旧 checkpoint JSONB 内嵌 writes；`alist()` 支持指定 checkpoint id、`before`、metadata
filter 和 filter 后 limit，并明确要求 thread config，不支持跨会话扫描。

`engine/tests/test_checkpoint_process_recovery.py` 会让真实 StateGraph/asyncpg worker 写入后由
父进程发送 `SIGKILL`，再由新进程恢复同一 thread 并继续动作。该核心恢复闭环已在 T-2.3
完成；REST 请求生命周期和生产 API 进程恢复仍需等 T-2.6 接线后验证。

当前这套 core 引擎已有独立测试覆盖，但 REST `/actions` 路由还没有切换过来。Agent 生成的 NPC/DM 回复属于 T-2.5；REST-StateGraph 接线、JWT WebSocket 绑定和玩法事件流仍属于 T-2.6。同一 session 的动作还没有跨 API 进程串行化，进程内 `asyncio.Lock` 或 checkpoint saver 锁都不能防止多个 worker 从同一检查点产生分支；这是 T-2.6 REST 接线前必须完成并通过多进程并发测试的阻断项。

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

文档和依赖提到了 LangGraph、agents、RAG、媒体编排、条件 DSL 和评分。LangGraph core 引擎和条件 DSL 阶段推进已经实现；当前实现主要在这些位置仍是骨架：

- `engine/agents/`
- `engine/rag/`
- `engine/media/orchestrator.py`
- `engine/services/scoring_service.py`

未来工作应通过现有 service/repository 边界集成这些功能，而不是绕过持久化和授权。
