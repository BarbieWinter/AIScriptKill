# 数据与运维

## 环境和配置

后端配置位于 `engine/api/config.py`，读取项目根目录 `.env` 和系统环境变量。当前配置项包括：

- Supabase/database：
  - `SUPABASE_PROJECT_REF`，默认 `local`。
  - `SUPABASE_URL`、`SUPABASE_PUBLISHABLE_KEY`、`SUPABASE_SECRET_KEY`。
  - `SUPABASE_STORAGE_BUCKET`，默认 `script-assets`；后端会强制 bucket 为私有。
  - `DATABASE_URL`；`DATABASE_POOLER_URL` 可选，存在时运行期优先使用。
  - `SUPABASE_JWT_AUDIENCE`，默认 `authenticated`。
- API：
  - `CORS_ORIGINS`，默认本地前端 origins。
  - `RATE_LIMIT_PER_MINUTE`，默认 120。
- MP-0 预留开关：
  - `MULTIPLAYER_V1=false`。
  - `ROOM_EVENTS_V1=false`。
  - `AI_DM_V1=false`。
- RAG embedding：
  - `RAG_EMBEDDING_PROVIDER`，取值 `deterministic` 或 `dashscope`，默认 `deterministic`。
  - `RAG_EMBEDDING_DIMENSIONS`，固定为 1024。
  - `RAG_DASHSCOPE_EMBEDDING_MODEL`，固定为 `text-embedding-v4`。
  - `DASHSCOPE_BASE_URL`，默认 DashScope OpenAI-compatible URL。
  - `DASHSCOPE_API_KEY`，使用 DashScope 时由服务端提供。
- NPC 生成：
  - `NPC_GENERATION_PROVIDER`，取值 `deterministic` 或 `openai_compatible`，默认 `openai_compatible`。
  - `OPENAI_API_KEY`、`OPENAI_BASE_URL`、`OPENAI_MODEL`；三项完整时才创建兼容 Chat Completions 客户端。
  - `NPC_OPENAI_MAX_TOKENS`，默认 512，范围 64–2048。
  - `NPC_OPENAI_TIMEOUT_SECONDS`，默认 20 秒，范围 1–60 秒。

三个 MP-0 开关当前都默认关闭，而且只是配置面：即使设为 `true`，也不会挂载新的 HTTP/WebSocket 入口，不会创建多人房间、事件流、AI-DM、数据库或前端 UI。当前公开 WebSocket 仍只有未认证的有界 ping/pong 心跳。

`.env.example` 只作为模板，不应提交真实 Supabase/database/provider 密钥。浏览器代码必须使用 FastAPI `/api/v1` 表面，而不是直接访问数据库。

后端数据库 engine 使用 asyncpg 的异步 SQLAlchemy。`engine/db/session.py` 会把 `postgresql://` 转成 `postgresql+asyncpg://`，启用 pool pre-ping 和较小连接池；本地数据库不强制 SSL，远程连接设置 `ssl=require`。

## Supabase/Postgres Schema

`supabase/migrations/` 下的迁移定义数据库形态：

- `001_script_tables.sql`：剧本包结构表：packages、stages、characters、clues、evidences、scenes、media。
- `002_runtime_tables.sql`：运行期表：sessions、checkpoints、chat messages、discoveries、final submissions、reviews。
- `003_vector_tables.sql`：`script_knowledge` pgvector 表。
- `004_rls_policies.sql`：早期 service-role、认证玩家和阶段/角色过滤策略。
- `005_runtime_persistence_indexes.sql`：会话、剧本包、状态、复盘、检查点和卡牌查询索引。
- `006_api_role_privileges.sql`：anon/authenticated/service_role 授权及早期公开包策略。
- `007_schema_comments.sql`：Phase 1 表、字段和 RLS policy 注释。
- `008_package_import_resolution_tables.sql`：`script_endings` 和 service-role-only 的 `script_dm_guides`。
- `009_restrict_package_private_tables.sql`：撤销 anon/authenticated 对结局和 DM 指引表的直接权限。
- `20260711073629_fastapi_data_access_boundary.sql`：撤销 anon/authenticated 对剧本内容、RAG 和运行时表的直接权限，统一通过 FastAPI 字段投影访问。
- `20260711105015_checkpoint_idempotency.sql`：清理重复 checkpoint，并为 `(session_id, thread_ts)` 建唯一索引。
- `20260711143000_checkpoint_pending_writes.sql`：建立 service-role-only 的规范化 LangGraph pending-writes 表。
- `20260711150000_checkpoint_column_comments.sql`：补充 checkpoint 列注释。
- `20260713000000_character_chapters.sql`：建立 service-role-only 的 `script_character_chapters`，保存严格 Markdown 章节及发布元数据；正文不自动进入普通 RAG 索引。
- `20260713010000_character_chapter_discoveries.sql`：允许 `session_discoveries.entity_type='character_chapter'`，以 `unlocked`/`viewed` 表示发放和阅读，并保持单调进度。
- `20260713020000_rag_embedding_v4_1024.sql`：清空不可安全转换的派生知识行，把 embedding 列迁为 1024 维并重建 IVFFlat 索引。
- `20260713030000_runtime_message_idempotency.sql`：为 `chat_messages` 增加 `engine_message_id` 及 `(session_id, engine_message_id)` 唯一索引，使图状态消息投影可幂等重放。

`supabase/seed/dev_seed.sql` 是旧 Phase 1 seed，不是当前 `script-packages/snow-village` YAML 单人垂直切片。它仍使用标题“雪乡连环杀人事件”、入口 `prologue`、旧场景/阶段和最多 4 人配置，并构造 1536 维向量；当前迁移后的列是 `vector(1024)`。因此不能把 `make db-reset` 应用这个 seed 后的内容描述为当前可执行雪村包，且 1536 维 seed 行与现有 schema 不兼容。当前 live 验收应导入并发布 `script-packages/snow-village`，直到 seed 被同步。

剧本包素材上传使用 `engine/core/package_storage.py` 中的 Supabase Storage 客户端。它通过 Supabase secret key 创建或修正私有 bucket，并只返回 `storage://<bucket>/<object>` 定位符。该定位符不是浏览器 URL；当前展示投影只接受同源路径或有效 HTTP(S) URL，签名 URL/代理下载仍未实现。

`engine/db/tables.py` 为 SQLAlchemy Core 查询镜像 public 表。修改 schema 时，需保持迁移和表元数据一致。

`SupabaseSessionCheckpointSaver` 把 checkpoint/metadata 编码在 `session_checkpoints.state`，并把 pending writes 独立写入 `session_checkpoint_writes`。后者允许 write-before-checkpoint，以复合主键保证多 saver/多进程重试幂等。每个 saver 写操作自行 `commit()`；调用方必须提供专用 `AsyncSession`，不得复用业务请求事务。恢复时会合并规范化 writes 与旧内嵌 writes。

## RLS 和权限

当前防剧透边界是 FastAPI 授权和字段投影，RLS 作为纵深防御而不是浏览器查询接口：

- `service_role` 和后端数据库角色可访问剧本、RAG 和运行期表。
- `20260711073629_fastapi_data_access_boundary.sql` 已撤销 anon/authenticated 对剧本内容、catalogue、RAG 和运行期表的权限，并删除对应 player/public policies。
- 浏览器只能调用 FastAPI。服务层根据当前阶段、角色和发现状态过滤线索、证据、章节、场景和会话数据。
- `script_endings`、`script_dm_guides`、`script_character_chapters` 和 `script_knowledge` 只能由服务端读取。

应用层仍需仔细审查：匿名会话使用 `player_id = NULL`，只要 UUID 已知，当前服务层访问检查就会允许访问。剧本包导入和状态变更额外受管理员 FastAPI 依赖保护；该依赖只信任 Supabase `app_metadata`。

## 本地开发

README 和根目录 `Makefile` 提供常用命令入口。

后端：

```bash
make dev-api
make test
make test-checkpoint-recovery
make verify-dev-tools
```

前端：

```bash
npm --prefix apps/web install
make dev-web
npm --prefix apps/web run build
npm --prefix apps/web run start
npm --prefix apps/web run lint
```

`make dev` 同时启动后端和前端。`make db-start` 启动本地 Supabase；`make db-reset` 会应用迁移并执行上述旧 seed，因此在 seed 同步前不能单独建立当前 live YAML 垂直切片。

`docker-compose.yml` 包含 `engine`、`web` 和本地 Supabase 镜像服务，并引用现有的 `engine/Dockerfile`、`apps/web/Dockerfile`。Compose 预期 `.env`，真实密钥不能写入文档。

## 运行期事务和测试状态

生产 REST action 已连接 LangGraph：

```text
POST /sessions/{id}/actions
  -> session_service.perform_action
  -> LangGraphRuntimeActionExecutor
  -> PostgreSQL advisory lock
  -> published package reconstruction + checkpoint restore/bootstrap
  -> YAML ScriptEngine/StateGraph action
  -> checkpoint commit
  -> session/chat/discovery projection commit
```

同一会话动作由独立连接上的事务级 `pg_advisory_xact_lock` 跨进程串行化。checkpoint saver 使用另一专用会话并自行提交，业务投影使用请求会话提交；锁事务、checkpoint 事务和投影事务不是一个原子事务。图消息使用 `engine_message_id` 去重，发现记录使用 upsert，投影前还会把线索、证据查看、章节阅读和证物出示等六类单调进度合并回图状态。

`engine/tests` 已覆盖 API 契约/JWT/WebSocket 边界、权限迁移、剧本包解析与导入、条件 DSL、StateGraph、RAG、人物章节、展示投影、runtime mapper、checkpoint codec/pending writes/并发和真实 PostgreSQL `SIGKILL` 恢复。前端有 build/lint scripts，但 `apps/web/package.json` 没有明确测试 runner。

后续回归测试应优先覆盖：

- REST 动作下 checkpoint 与 session/chat/discovery 投影的一致性。
- advisory lock 下同会话并发、多 worker 重试和“checkpoint 已提交但投影失败”等故障行为。
- `engine_message_id` 与 discovery upsert 的重复投影幂等性。
- 人物章节和证据状态的单调升级、角色授权与防剧透。
- 当前 YAML 包导入/发布后的 `/demo/live` 全链路。
- 保持本地 Supabase anon/authenticated 拒绝探针，防止迁移意外恢复直接表权限。

## 运维注意事项

- 真实凭据只放 `.env` 或部署环境。
- `/health/db` 要求 `script_knowledge` 等必要表存在；使用前确保迁移完整。
- 浏览器表访问应始终被拒绝；保持 RLS、角色 grants、service-role 使用和 FastAPI 应用层检查同步。
- 三个 MP-0 flag 不是部署完成信号；当前没有多人运行时、房间事件持久化、认证事件 WebSocket 或多人 UI。
