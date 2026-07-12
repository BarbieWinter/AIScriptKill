# AI Script Kill — AI 沉浸式悬疑互动剧系统

基于固定精品剧本的 AI 沉浸式悬疑互动游戏引擎。

## 项目结构

```
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
├── script-packages/      # 剧本包集合（数据，可插拔）
│   └── snow-village/     # 《雪乡连环杀人事件》
├── supabase/             # Supabase 迁移与种子数据
└── docs/                 # 设计文档
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

# 启动本地 Supabase（Colima 环境默认跳过日志采集服务）
make db-start

# 重置本地 Supabase（需要先启动本地 Supabase）
make db-reset

# 本地 Supabase 上验证 StateGraph 进程强杀恢复
make test-checkpoint-recovery

# 同时启动后端和前端
make dev

# 只启动后端
make dev-api

# 只启动前端
make dev-web
```

## 设计文档

- `docs/ARCHITECTURE_OVERVIEW.md` — 系统架构总览
- `docs/SCRIPT_PACKAGE_SCHEMA.md` — 剧本包 Schema 规范
- `docs/CONDITION_DSL_REFERENCE.md` — 条件 DSL 参考
- `docs/API_REFERENCE.md` — API 契约
- `docs/FRONTEND_EXPERIENCE_DESIGN.md` — 前端交互体验设计
- `docs/EXECUTION_PLAN.md` — 执行计划书
