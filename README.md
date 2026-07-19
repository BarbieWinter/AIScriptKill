# AI Script Kill — AI 沉浸式悬疑互动剧系统

基于固定精品剧本的 AI 沉浸式悬疑互动游戏引擎。

## 当前可运行切片

仓库保留单人垂直切片 `snow-village`：**《雪落之前：后门的脚印》**，并已加入
`mp1-two-player` 的无网络多人阶段状态机，以及 MP-2 房间大厅的 persistence/snapshot/auth/schema
与前端基础。MP-2 room repository/service/routes 已集成，并通过 focused/full engine、Ruff、focused
BasedPyright 与 app/OpenAPI build；真实 PostgreSQL concurrency/privilege 和 live-stack Playwright 仍为
**BLOCKED / NOT RUN**，因此多人大厅仍是 **IN PROGRESS / NOT RELEASE-READY**。

单人前端演示入口：

- `/demo`：选择 Live 或 Mock；
- `/demo/live/{sessionId}`：连接真实 Session API、已发布 YAML 包和 LangGraph 状态；
- `/demo/mock/{sessionId}`：浏览器内临时数据，刷新会重置，不代表后端持久化行为。

单人流程仍使用 `snow-village` 的卓司元角色，覆盖人物章节、王大达对话、后巷热点、证物查看/出示和
阶段判断。多人前端已增加 `/multiplayer`、`/invite/[token]` 与
`/play/[sessionId]/lobby`；这些页面使用 Supabase anonymous session 和 HTTP lobby contract，进入
`active` 后只展示 MP-6 后续接入提示，不使用现有 legacy gameplay 或 application WebSocket。默认
Playwright 命令通过的是 mocked-contract 测试，不是真实 Supabase/FastAPI/PostgreSQL E2E；仓库另有显式
`make test-mp2-live` lane，它只连接已经启动的真实栈，前置条件缺失时失败并报告 `BLOCKED`，不会回退到 route mocks。

Live 创建固定使用 `script_id: snow-village`、角色 `zhuosiyuan`。启动前必须将当前 `script-packages/snow-village/` 归档通过管理员 `POST /api/v1/packages?publish=true` 导入并发布。`supabase/seed/dev_seed.sql` 是旧阶段的开发种子，标题、入口阶段、场景和材料均已过期，不能作为当前 Live 演示的数据来源。

## 项目结构

```text
AIScriptKill/
├── engine/               # Python 后端（FastAPI + LangGraph + RAG）
│   ├── core/             # 引擎内核（StateGraph/条件评估/剧本包加载）
│   ├── agents/           # AI Agent（DM/NPC/Guard/Hint）
│   ├── rag/              # RAG 检索系统
│   ├── media/            # 多媒体编排
│   ├── services/         # 业务服务
│   ├── api/              # FastAPI 网关
│   └── tests/            # 测试
├── apps/web/             # Next.js 前端
├── script-packages/
│   └── snow-village/     # 《雪落之前：后门的脚印》单人垂直切片
├── supabase/             # Supabase 迁移与旧开发种子
└── docs/                 # 设计与契约文档
```

## 快速开始

```bash
# 安装依赖
make install

# 验证锁文件中的后端开发工具
make verify-dev-tools

# 后端测试、静态检查与严格类型检查
make test
make lint-api
make typecheck-api

# 启动并重置本地 Supabase
make db-start
make db-reset

# 同时启动后端和前端
make dev

# 也可分别启动
make dev-api
make dev-web
```

`make dev` 会让 Next.js 将 `/api/*` 代理到 `http://localhost:8000`。数据库重置后仍需按上文说明重新导入并发布当前剧本包，才能创建 Live 会话。

### MP-2 本地手动大厅

MP-2 使用 host-run FastAPI/Next + 本地 Supabase CLI。先确认命令是在目标 checkout 根目录执行，且 `.env`
包含本地 Supabase URL、公开 publishable key、服务端 secret key 和本地 direct `DATABASE_URL`；不要把这些值
提交到仓库。数据库 migration/reset 和 `mp1-two-player` 发布是独立的持久化操作，必须明确执行，不会由启动
命令隐式触发。

```bash
# 1. 在本地 Supabase 已启动、migration 已应用且 mp1-two-player 已发布后启动真实栈
make dev-mp2

# 2. 基础检查
curl --fail http://127.0.0.1:8000/health/db
curl --fail http://127.0.0.1:3000/multiplayer

# 3. 真实双身份浏览器 lane（绝不拦截 Auth 或 /api/v1）
make test-mp2-live
```

手动走查时，房主使用普通浏览器 profile，受邀者必须使用另一个 profile 或独立无痕 context；普通两个 tab
会共享同一个 Supabase anonymous identity。依次验证创建、邀请 URL、接受邀请、不同角色、ready/unready、
换角清 ready、房主开始。开始后显示“房间已原子启动”和 MP-6 placeholder 属于当前预期。

如果没有已迁移的 disposable/local PostgreSQL、可用的 anonymous Auth 或已发布的 `mp1-two-player`，live lane
必须保持 `BLOCKED / NOT RUN`，不能用 mocked-contract 结果代替。

其他验证命令：

```bash
make test-checkpoint-recovery
make test-database-privileges
make test-mp2-contract
make test-mp2-live
make lint-web
```

## 设计文档

- `docs/ARCHITECTURE_OVERVIEW.md` — 系统架构总览
- `docs/SCRIPT_PACKAGE_SCHEMA.md` — 剧本包 Schema 规范
- `docs/CONDITION_DSL_REFERENCE.md` — 条件 DSL 参考
- `docs/API_REFERENCE.md` — 当前 REST、MP-2 HTTP contract 状态与 WebSocket 边界
- `docs/MULTIPLAYER_ARCHITECTURE_PLAN.md` — 多人阶段路线、MP-2 进行中状态与发布 gate
- `docs/adr/0005-immutable-runtime-package-snapshot.md` — 房间冻结 runtime package 的决定
- `docs/reports/mp-2-room-lobby-2026-07-18.md` — MP-2 已验证证据、阻断项与非发布判定
- `docs/FRONTEND_EXPERIENCE_DESIGN.md` — 前端交互体验设计
- `docs/EXECUTION_PLAN.md` — 执行计划书
