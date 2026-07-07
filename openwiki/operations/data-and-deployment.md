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

`supabase/seed/dev_seed.sql` 提供最小雪乡验收数据，包括已发布剧本包、阶段、角色、场景、线索、证物、媒体和一条 pgvector 知识分块。

`engine/db/tables.py` 为 SQLAlchemy Core 查询镜像了大多数 public 表。修改 schema 时，保持迁移和表元数据一致。

## RLS 和权限

RLS 是防剧透控制的核心。当前策略设计包括：

- `service_role` 对剧本和运行期表有完整访问权。
- 通过 `006_api_role_privileges.sql` 让 anon/authenticated 用户可见已发布剧本包。
- 认证玩家可以访问自己的会话和相关运行期数据。
- 线索/证据/场景可见性可以依赖当前阶段和玩家角色 setting。
- `script_knowledge` 明确不打算让玩家直接查询；RAG 应在服务端查询，并强制应用阶段/角色上下文。

应用层行为仍需仔细审查。后端匿名会话目前使用 `player_id = NULL`，只要 UUID 已知，服务层访问检查就会允许访问。

后端剧本包导入和剧本包状态变更还额外受仅管理员可用的 FastAPI 依赖保护。该依赖信任 Supabase `app_metadata`，不信任用户可编辑 metadata。

## 本地开发

README 和根目录 `Makefile` 提供常用命令入口。

后端：

```bash
make dev-api
make test
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

当前 `engine/tests` 包含 `engine/tests/test_admin_auth.py` 中针对剧本包导入/状态管理的管理员授权测试，以及 `engine/tests/test_package_loader.py` 和 `engine/tests/package_loader_fixtures.py` 中的剧本包 loader 测试。loader 覆盖最小包、目录入口、manifest-to-stage 引用、阶段角色/线索轮次引用、重复线索 id、action object 归一化、事件动作校验、证据 NPC 引用、本地素材缺失和角色阶段知识 warning。目前仍没有对会话持久化、玩法动作或 RLS 敏感查询的广泛后端覆盖。

前端 scripts 包含 build 和 lint 命令，但 `apps/web/package.json` 中没有配置明确的测试 runner。

添加测试时，优先覆盖：

- 剧本包导入到数据库的替换行为和 warnings 持久化/暴露策略。
- 基于已导入剧本包 fixtures 创建会话。
- 动作副作用和检查点持久化。
- 如果测试可连接 Supabase/Postgres，则覆盖 RLS 敏感查询行为。
- Mock/真实边界和会话创建相关的前端路由行为。

## 运维注意事项

- `.env.example` 是安全模板；真实凭据只放 `.env` 或部署环境。
- Docker Compose 引用的 Dockerfile 已存在。
- 后端健康检查要求存在 `script_knowledge`；使用 `/health/db` 前确保已应用向量迁移。
- 直接表访问和后端 API 访问使用不同安全模型。保持 RLS、service-role 使用和应用层检查同步。
