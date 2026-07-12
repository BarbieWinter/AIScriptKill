# 数据与运维

## 环境和配置

后端配置位于 `engine/api/config.py`。它预期这些环境变量：

- `SUPABASE_PROJECT_REF`，可选。
- `SUPABASE_URL`。
- `SUPABASE_PUBLISHABLE_KEY`。
- `SUPABASE_SECRET_KEY`。
- `DATABASE_URL`。
- `DATABASE_POOLER_URL`，可选，存在时运行期优先使用。
- `CORS_ORIGINS`，默认本地前端 origins。
- `RATE_LIMIT_PER_MINUTE`，默认 120。
- `SUPABASE_JWT_AUDIENCE`，默认 `authenticated`。
- `SUPABASE_STORAGE_BUCKET`，默认 `script-assets`，后端会强制 bucket 为私有。

当前注意点：后端运行期读取项目根目录 `.env` 和系统环境变量；`.env.example` 只作为模板，不应提交真实 Supabase/database 密钥。浏览器代码必须使用 FastAPI `/api/v1` 表面，而不是直接访问数据库。

后端数据库 engine 是使用 asyncpg 的异步 SQLAlchemy。`engine/db/session.py` 会把 `postgresql://` 转成 `postgresql+asyncpg://`，启用 pool pre-ping，使用较小连接池；本地数据库不强制 SSL，远程连接会设置 `ssl=require`。

## Supabase/Postgres Schema

`supabase/migrations/` 下的迁移定义数据库形态：

- `001_script_tables.sql`：剧本包结构表：packages、stages、characters、clues、evidences、scenes、media。
- `002_runtime_tables.sql`：运行期表：sessions、checkpoints、chat messages、discoveries、final submissions、reviews。
- `003_vector_tables.sql`：未来 RAG 使用的 `script_knowledge` pgvector 表，带 1536 维 embedding 列和 IVFFlat 索引。
- `004_rls_policies.sql`：启用 RLS，并为 service-role 访问、认证玩家自有会话数据、阶段/角色过滤的剧本内容定义策略。
- `005_runtime_persistence_indexes.sql`：会话/剧本包/状态/复盘/检查点/卡牌查询的补充索引。
- `006_api_role_privileges.sql`：anon/authenticated/service_role 授权，以及已发布剧本包的公开策略。
- `007_schema_comments.sql`：为 Phase 1 表、字段和 RLS policy 补充注释。
- `008_package_import_resolution_tables.sql`：`script_endings` 和仅 service-role 可访问的 `script_dm_guides`。
- `009_restrict_package_private_tables.sql`：显式撤销 anon/authenticated 对 `script_endings` 和 `script_dm_guides` 的全部直接权限。
- `20260711073629_fastapi_data_access_boundary.sql`：撤销 anon/authenticated 对剧本内容、
  RAG 知识和运行时表的直接权限，统一通过 FastAPI 字段投影访问。
- `20260711105015_checkpoint_idempotency.sql`：清理历史重试产生的重复 checkpoint，并为 `(session_id, thread_ts)` 建立唯一索引。
- `20260711143000_checkpoint_pending_writes.sql`：为 LangGraph pending writes 建立独立、
  service-role-only 的幂等表。

`supabase/seed/dev_seed.sql` 提供最小雪乡验收数据，包括已发布剧本包、阶段、角色、场景、线索、证物、媒体和一条 pgvector 知识分块。

剧本包素材上传使用 `engine/core/package_storage.py` 中的 Supabase Storage 客户端。它通过
Supabase secret key 创建或修正私有 bucket，并只返回 `storage://<bucket>/<object>` 定位符。
不要把该定位符当作浏览器 URL；T-2.6 应在鉴权和会话可见性检查后生成短期签名 URL 或
由 FastAPI 代理下载。

`engine/db/tables.py` 为 SQLAlchemy Core 查询镜像了大多数 public 表。修改 schema 时，保持迁移和表元数据一致。

`SupabaseSessionCheckpointSaver` 把 checkpoint/metadata 编码在 `session_checkpoints.state`，
并把 pending writes 独立写入 `session_checkpoint_writes`。后者允许 write-before-checkpoint，
用复合主键保证多 saver/多进程重试幂等。每个写操作自己 `commit()`；调用方必须提供专用
`AsyncSession`，不得复用业务请求事务。恢复时会合并规范化 writes 与旧内嵌 writes。

## RLS 和权限

当前防剧透边界是 FastAPI 授权和字段投影，RLS 作为纵深防御而不是浏览器查询接口：

- `service_role` 和后端数据库角色对剧本、RAG 和运行期表拥有服务端访问权。
- `004_rls_policies.sql` 与 `006_api_role_privileges.sql` 保留了早期的直接访问设计历史；
  `20260711073629_fastapi_data_access_boundary.sql` 已撤销 anon/authenticated 对所有剧本内容、
  catalogue、RAG 和运行期表的权限，并删除对应 player/public policies。
- 浏览器只能调用 FastAPI。已发布剧本目录由 API 返回受控字段，线索、证据、场景和会话
  数据由服务层结合当前阶段、角色和发现状态过滤。
- `script_endings`、`script_dm_guides` 和 `script_knowledge` 只能由服务端读取，避免结局、
  DM 真相和未授权 RAG 内容绕过应用层泄露。

应用层行为仍需仔细审查。后端匿名会话目前使用 `player_id = NULL`，只要 UUID 已知，服务层访问检查就会允许访问。

后端剧本包导入和剧本包状态变更还额外受仅管理员可用的 FastAPI 依赖保护。该依赖信任 Supabase `app_metadata`，不信任用户可编辑 metadata。

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

`make dev` 会同时启动后端和前端，并让前端连接本地后端 WebSocket。`make db-start` 启动本地 Supabase，`make db-reset` 应用迁移和 `supabase/seed/dev_seed.sql`。

`docker-compose.yml` 中存在 Docker Compose，包含 `engine`、`web` 和本地 Supabase 镜像服务。它引用 `engine/Dockerfile` 和 `apps/web/Dockerfile`。Compose 预期 `.env`，其中应包含本地密钥，不能写入文档。

## 测试状态

后端测试配置位于 `pyproject.toml`：

- 测试路径：`engine/tests`。
- `pytest-asyncio` 模式：auto。
- Ruff 目标：Python 3.12，行宽 100，启用 lint families `E`、`F`、`I`、`N`、`W`。

当前 `engine/tests` 包含 API 契约/请求体/JWT/WebSocket 边界、数据库权限迁移、严格剧本
包解析与导入、完整条件 DSL、StateGraph 迁移/事件/动作，以及 checkpoint codec、并发 saver、
write-before-checkpoint 和真实 PostgreSQL `SIGKILL` 恢复测试。进程测试默认独立运行，使用
`AISCRIPTKILL_PROCESS_RECOVERY_DB_URL` 或本地 Supabase URL。REST action endpoint 仍未接入
core StateGraph；该 API 级集成与并发会话队列属于 T-2.6。

前端 scripts 包含 build 和 lint 命令，但 `apps/web/package.json` 中没有配置明确的测试 runner。

添加测试时，优先覆盖：

- 剧本包导入到数据库的替换行为和 warnings 持久化/暴露策略。
- 基于已导入剧本包 fixtures 创建会话，并让 REST action endpoint 调用 core StateGraph。
- T-2.6 接线后的 REST 动作到 StateGraph/检查点全链路，以及 API 进程重启恢复。
- 保持本地 Supabase 的 anon/authenticated 拒绝探针，防止后续迁移意外恢复直接表权限。
- Mock/真实边界和会话创建相关的前端路由行为。

## 运维注意事项

- `.env.example` 是安全模板；真实凭据只放 `.env` 或部署环境。
- Docker Compose 引用的 Dockerfile 已存在。
- 后端健康检查要求存在 `script_knowledge`；使用 `/health/db` 前确保已应用向量迁移。
- 浏览器表访问应始终被拒绝；保持 RLS、角色 grants、service-role 使用和 FastAPI 应用层检查同步。
