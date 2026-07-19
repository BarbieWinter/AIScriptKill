# 后端架构

## 入口和中间件

后端入口是 `engine/api/main.py`。`create_app()` 构建 FastAPI 应用并安装：

- `engine/api/errors.py` 的 `ApiError` 和数据库异常处理器。
- `engine/api/middleware/body_limit.py` 的累计 ASGI 请求体限制：普通请求 1 MiB，剧本包 multipart 信封 65 MiB；chunked 请求同样受限。
- `engine/api/middleware/rate_limit.py` 的按客户端内存限流。
- `engine/api/config.py` 的 CORS origins。
- sessions、actions、packages 和 WebSocket 路由。
- `/health` 和 `/health/db`。

`/health/db` 调用 `engine/db/session.py::check_database_connection()`，验证连接和必要 public 表，包括 `script_knowledge`。

## 配置

`engine/api/config.py` 使用 Pydantic settings。它涵盖 Supabase/database、CORS/限流、JWT audience、三个默认关闭且无入口的 MP-0 预留 flag、1024 维 RAG embedding provider，以及 OpenAI-compatible NPC provider。完整变量和默认值见[数据与运维](../operations/data-and-deployment.md)。

settings 读取项目根目录 `.env` 和系统环境变量；`.env.example` 只保留占位符。存在 `DATABASE_POOLER_URL` 时优先使用它，否则使用 `DATABASE_URL`。普通 `postgresql://` 会转换为 `postgresql+asyncpg://`；本地数据库不强制 SSL，远程连接使用 `ssl=require`。

## 认证和授权

`engine/api/middleware/auth.py` 定义跨路由依赖：

- 无 bearer token：返回 `CurrentUser(subject="anonymous", role="anonymous")`。
- 有 bearer token：根据项目 JWKS 校验 Supabase JWT 的签名、issuer、audience、有效期和必需 claims。
- 剧本包导入和状态更新仅允许管理员；只信任 Supabase `app_metadata.role` / `app_metadata.roles`，不信任用户可编辑 metadata。

会话访问由 `engine/services/session_service.py` 强制执行。如果 `game_sessions.player_id` 为 `NULL`，任何知道会话 UUID 的人都能访问；设置了 `player_id` 时，必须匹配已认证 Supabase user id。

浏览器没有底层剧本、RAG、章节和运行时表权限。服务端访问和字段投影是主边界，RLS 是纵深防御。

## API 路由

### Sessions

`engine/api/routes/sessions.py` 暴露：

- `POST /api/v1/sessions`：从已发布剧本包和指定角色创建会话。
- `GET /api/v1/sessions/{session_id}`：当前会话状态摘要。
- `GET /api/v1/sessions/{session_id}/presentation`：当前阶段/场景的防剧透展示投影。
- `PATCH /api/v1/sessions/{session_id}`：公开恢复入口当前 fail closed，返回 409 `SESSION_RESTORE_UNAVAILABLE`，不会读取或恢复数据库 checkpoint。仓储仍保留内部/旧投影 checkpoint helper，不能据此认为公开恢复可用。
- `GET /api/v1/sessions/{session_id}/clues`：已解锁线索。
- `GET /api/v1/sessions/{session_id}/evidences`：已发现证据。
- `POST /api/v1/sessions/{session_id}/evidences/{evidence_id}/viewed`：把已发现证据单调升级为已查看。
- `GET /api/v1/sessions/{session_id}/character-chapters`：当前玩家角色已授权章节目录。
- `GET /api/v1/sessions/{session_id}/character-chapters/{chapter_id}`：读取已授权 Markdown 正文并持久化已读状态。
- `GET /api/v1/sessions/{session_id}/characters`：当前可用角色。
- `GET /api/v1/sessions/{session_id}/chat-history`：已存储聊天历史。
- `GET /api/v1/sessions/{session_id}/cards`：从 card 类型 evidence 派生的可用卡牌。
- `GET /api/v1/sessions/{session_id}/review`：已完成复盘或未提交时的缺省复盘。

### Actions

`engine/api/routes/actions.py` 暴露：

- `POST /api/v1/sessions/{session_id}/actions`：执行真实 LangGraph/YAML 动作。
- `POST /api/v1/sessions/{session_id}/final-submission`：按当前阶段声明的 judgment option 评分并持久化复盘。

生产动作不再走 `engine/services/action_mappers.py` 中的王大达/`broken_glass`/`act1_event` 固定逻辑。该文件的旧 action mapper 没有被生产 `/actions` 引用；当前仍复用其中的最终判断结果 helper。

### Packages

`engine/api/routes/packages.py` 暴露：

- `POST /api/v1/packages`：管理员上传并导入 zip；`publish=true` 可在导入时发布。
- `PATCH /api/v1/packages/{package_id}`：管理员更新状态。
- `GET /api/v1/packages`：列出已发布剧本包。
- `GET /api/v1/packages/{package_id}`：读取一个已发布包的玩家安全详情。

导入会在 upsert package 后替换该 script id 的全部规范化结构行。前端只能通过 FastAPI，不能直接写 Supabase 表。

### WebSocket

`engine/api/websocket/handler.py` 接受 `/api/v1/ws/{session_id}`，其中 `session_id` 必须是 UUID。目前它是未认证的有界心跳端点：只消费 JSON 文本 `session.ping` 并返回 `session.pong`；binary 帧以 1003 关闭。连接管理器和 Uvicorn/应用层限制连接数、64 KiB 消息、接收队列、每分钟消息数和空闲时长。

这里没有 ticket/hello/ready、玩法事件、事件重放、presence 或 resync。`MULTIPLAYER_V1`、`ROOM_EVENTS_V1`、`AI_DM_V1` 即使打开也不会添加入口；认证房间事件流属于尚未实现的多人运行时，而不是当前 REST-StateGraph 接线的一部分。

## 服务层和仓储层

后端整体遵循 route -> service -> repository 分层。`engine/services/session_service.py` 协调会话访问、动作、提交和查询；`engine/repositories/session_repository.py` 是持久化门面，委托给：

- `session_seed.py`：从已发布包入口阶段、角色和阶段定义派生初始投影，并发放 game-start 章节。
- `session_mutations.py`：创建会话/旧投影 checkpoint、单调查看状态、动作投影、发现 upsert、提交和复盘。
- `session_queries.py`：加载会话、阶段、发现、章节、角色、聊天、卡牌和复盘。
- `session_context.py`：在可见性敏感查询前设置 `app.current_stage`、`app.player_character` 等 Postgres setting。
- `session_models.py`、`session_rows.py`：运行期状态和行映射。

### 生产动作执行链

生产路径是：

```text
actions route
  -> session_service.perform_action
  -> create_runtime_action_executor()
  -> LangGraphRuntimeActionExecutor.execute()
```

`engine/services/runtime_session.py` 的执行器：

1. 用独立 `SessionFactory` 连接取得 `pg_advisory_xact_lock(hashtextextended(session_id, 0))`，跨 API 进程串行化同一会话动作。
2. 在持锁范围内重新读取最新 session。
3. 通过 `engine/repositories/runtime_package_repository.py` 从已发布、规范化 `script_*` 行重建完整服务端 `ScriptPackageImport`，包括阶段、角色、人物章节、线索、证据、场景、媒体、结局和 DM 指引。
4. 创建专用 checkpoint `AsyncSession`，组装 `RagRetriever`、NPC responder 和 `ScriptEngine.from_package()`。
5. 优先恢复最新 LangGraph checkpoint；没有 checkpoint 时才从有限 session 投影 bootstrap。执行前把六类单调进度合并回图状态：线索、发现证据、已查看证据、已解锁章节、已读章节和已向 NPC 出示的证据。
6. 通过 `runtime_action_mappers.py` 把 REST 多字段载荷编码为 core target，执行 StateGraph，再把状态差量映射为 NPC 回复、场景发现、证物反应、阶段切换或未满足条件。
7. 通过 `runtime_state_mappers.py` 生成有限 session 投影，并把 session state、chat 和 discoveries 写回请求事务。

锁事务、checkpoint saver 事务和请求投影事务彼此分离，不是一次原子数据库提交。checkpoint saver 的 `aput`/`aput_writes` 会自行提交；投影随后单独提交。chat 通过 `(session_id, engine_message_id)` 唯一索引幂等，discoveries 使用不降级 upsert。这一设计能安全重放投影，但仍应测试 checkpoint 已提交而投影失败等故障窗口，不能描述成“checkpoint + revision + event + outbox 同事务”的多人写模型。

### 展示投影

`GET .../presentation` 使用 `get_runtime_package()` 定位当前阶段和场景，再由 `session_response_mappers.py` 白名单映射：

- stage：id、name、当前可用 actions 和 characters。
- scene：id、name、可选公开 description/ambient color、浏览器安全的同源或 HTTP(S) background URL。
- hotspots：保持包内顺序，只公开 id、label、x/y 和可选 width/height；private/DM-only 项会过滤，`on_click` 执行规则绝不返回。
- judgment：只公开 title、question 和有序 options；`correct_option` 保留在服务端评分路径。

### 人物章节

章节数据路径是：

```text
character_scripts/<character>/<chapter>.md
  -> package_character_chapter_loader.py
  -> package_character_chapter_yaml.py 严格 frontmatter
  -> script_character_chapters
  -> session_discoveries(character_chapter)
  -> 角色/会话授权后的 list/read API
```

frontmatter 支持 `game_start` 或带 `rule_id` 的 `rule` 发布、固定 `character_only` visibility 和可选 `stage_min`。`event_bus.py` 在开局或 `unlock_character_chapter` 事件中只为当前玩家角色发放章节。查询还要求章节属于 `player_character_id` 且当前 session 已有 discovery；读取将状态由 `unlocked` 单调升级为 `viewed`。章节正文明确不自动进入普通 `script_knowledge` RAG 索引。

## 剧本包导入

`engine/services/import_service.py` 通过 `engine/core/package_loader.py` 校验 zip，并用 `engine/repositories/package_import_repository.py` 写入。加载器已拆分为：

- `package_archive.py`、`package_directory.py`：归档过滤、根定位、YAML 读取及目录打包复用。
- `package_yaml.py`、`package_*_yaml.py`：strict 且 `extra="forbid"` 的输入模型。
- `package_records.py`：转换为 package/stage/character/chapter/clue/evidence/scene/media/ending 记录。
- `package_character_chapter_loader.py`、`package_character_chapter_yaml.py`：严格解析人物 Markdown 章节。
- `package_content_loader.py`：读取角色、章节、线索、证据、场景、媒体、`endings.yml`、`dm_guide/*.yml` 和 assets。
- `package_importer.py`、`package_storage.py`：可选上传 assets 到私有 bucket，并重写为 `storage://` 定位符。
- `package_validation*.py`：校验 IDs、引用、条件、事件和本地素材，返回知识缺失 warnings。

`engine/core/package_schema.py` 保存导入记录 dataclass。仓储写入公开结构表，以及仅服务端可访问的 endings、DM guides 和 character chapters；重复导入先删除旧结构再重建。

## StateGraph、RAG 和 NPC

`engine/core/script_engine.py` 用 LangGraph `StateGraph` 组装 `stage_entry`、`player_action`、`npc_response`、`check_conditions`、`process_events`、`stage_exit` 和 `ending` 节点。动作先验证当前阶段允许的 action/target；非法输入抛出稳定 `ScriptEngineActionError.code`，由 REST 映射成 400。

`engine/core/event_bus.py` 执行 `dm_narrate`、`play_audio`、`unlock_*`、`npc_*`、`transition_to` 等确定性事件。条件 DSL、阶段顺序和不可跳跃/不可回退约束均在 core 执行。

RAG 已实现 chunking、indexing、embedding provider factory、vector + BM25 检索、rerank 和按阶段/角色/线索授权过滤。生产动作会构建 `RagRetriever` 给 NPC responder 使用。

`engine/agents/npc_agent.py` 已实现真实 NPC 生成边界：

- 配置完整时使用 OpenAI-compatible Chat Completions；否则返回确定性 fallback。
- prompt 只包含当前角色、阶段、包内已授权知识、有限历史和通过 `RagRetriever` 过滤的片段。
- RAG/provider 失败会安全降级；生成文本为空、过长、包含包内 forbidden term，或新增未授权时间值时，也降级为“我只能说自己亲眼见过、亲耳听到的，没把握的事不能乱讲。”。
- NPC 只负责语言表达，不决定解锁、判断或状态变化；这些仍由 YAML/StateGraph 决定。

DM/Guard/Hint agent 尚未形成公开 AI-DM 运行时；`engine/media/orchestrator.py` 和通用 `scoring_service.py` 仍是后续集成面。当前单人判断提交使用阶段 YAML 的正确 option 做 100/0 确定性评分。

## Checkpoint 边界

`engine/core/checkpoint.py` 的 `SupabaseSessionCheckpointSaver` 以唯一 `(session_id, thread_ts)` upsert checkpoint；pending writes 使用 `(session_id, checkpoint_id, task_id, write_idx)` 复合主键，支持 write-before-checkpoint 和重试。读取兼容旧内嵌 writes；`alist()` 要求 thread config，不支持跨会话扫描。

真实 StateGraph/asyncpg `SIGKILL` 恢复测试验证的是 core checkpoint saver 的跨进程恢复。生产 REST action 已使用该 saver，但公开 `PATCH` 恢复仍 fail closed；不要把内部 checkpoint 恢复能力等同于面向客户端的任意历史回滚 API。
