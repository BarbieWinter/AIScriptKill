# AI Script Kill — AI 沉浸式悬疑互动剧系统

基于固定精品剧本的 AI 沉浸式悬疑互动游戏引擎。

## 当前可运行切片

仓库当前提供单人垂直切片 `snow-village`：**《雪落之前：后门的脚印》**。玩家以卓司元身份阅读人物章节、与王大达交谈、调查后巷热点、查看并出示“21:13 后门截图”，最后提交阶段判断。当前包为 `max_players: 1`；多人房间与多人运行时尚未接入。

前端演示入口：

- `/demo`：选择 Live 或 Mock；
- `/demo/live/{sessionId}`：连接真实 Session API、已发布 YAML 包和 LangGraph 状态；
- `/demo/mock/{sessionId}`：浏览器内临时数据，刷新会重置，不代表后端持久化行为。

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

其他验证命令：

```bash
make test-checkpoint-recovery
make test-database-privileges
make lint-web
```

## 设计文档

- `docs/ARCHITECTURE_OVERVIEW.md` — 系统架构总览
- `docs/SCRIPT_PACKAGE_SCHEMA.md` — 剧本包 Schema 规范
- `docs/CONDITION_DSL_REFERENCE.md` — 条件 DSL 参考
- `docs/API_REFERENCE.md` — 当前 REST 与 WebSocket 契约
- `docs/FRONTEND_EXPERIENCE_DESIGN.md` — 前端交互体验设计
- `docs/EXECUTION_PLAN.md` — 执行计划书
- `docs/MULTIPLAYER_ARCHITECTURE_PLAN.md` — 多人联机架构与执行计划书
