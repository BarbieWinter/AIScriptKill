# OpenWiki 快速开始

## 这个仓库是什么

AIScriptKill 是一个 AI 辅助的沉浸式剧本杀游戏系统。产品方向是固定、高质量的剧本包，加上 AI 演绎、控场、线索/证据发现、媒体氛围、最终推理和复盘。最清晰的产品表述在 `/doc/剧本系统设计.md`：AI 应该在固定剧本边界内表演，而不是改写谜题、更换凶手或发明关键证据。

仓库目前包含四个主要区域：

- `engine/`：Python 3.12 FastAPI 后端，包含剧本包导入、运行期持久化服务、Supabase/Postgres 访问，以及 AI/RAG/媒体模块骨架。
- `apps/web/`：Next.js 15 React 19 前端，用于剧本库浏览、角色选择、游玩和复盘。
- `supabase/migrations/`：Postgres schema、pgvector 知识表、RLS 策略、索引和 API 角色授权。
- `docs/` 和 `doc/`：已有架构、API、剧本包 schema、前端设计、执行计划，以及中文产品/领域设计文档。

近期 git 历史显示仓库是分层构建的：先导入产品和资产，再搭系统脚手架、前端架构和后端架构。本 OpenWiki 有意放在根目录 `/openwiki`。

## 当前实现现状

现有设计文档是重要意图来源，但改代码前必须以源码验证实际行为。

已经实现的部分：

- `engine/api/` 中的 FastAPI 应用组装、CORS、限流、错误处理、会话/剧本包/动作路由、剧本包详情查询和 WebSocket 心跳。
- `engine/db/session.py` 中基于异步 SQLAlchemy 的 Supabase/Postgres 访问，以及 `engine/db/tables.py` 中的表元数据。
- `engine/core/package_loader.py` 及其 `package_archive.py`、`package_directory.py`、`package_yaml.py`、`package_records.py`、`package_validation*.py` 等拆分模块中的剧本包 zip/目录导入、YAML 解析、记录归一化和引用/资产校验。
- 通过 `engine/services/` 和 `engine/repositories/` 实现的运行期会话创建、检查点恢复、确定性动作效果、最终提交持久化和复盘查询。
- Next.js 页面：`/library`、`/library/[id]`、`/play/[sessionId]/select`、`/play/[sessionId]` 和 `/play/[sessionId]/review`。
- `apps/web/lib/mock-data.ts` 和 `apps/web/lib/mock-ws.ts` 中的前端 Mock 玩法数据和 Mock WebSocket。

目前主要仍是愿景或占位的部分：

- LangGraph 状态机、条件求值器、事件总线、检查点抽象、AI Agent、RAG 检索/切分/重排、媒体编排器和评分服务还是骨架或仅有注释的模块。
- 主前端玩法在 `NEXT_PUBLIC_USE_MOCK=false` 时会读取真实后端 session 并接入真实 WebSocket 心跳；具体玩法事件、热点和部分组件仍主要依赖 Mock 引擎。
- `script-packages/snow-village` 有预期目录骨架，但没有 `package.yml` 或 YAML 内容。
- LangGraph/RAG/媒体/评分等高级能力仍是后续阶段工作。

## 从哪里开始

- 架构总览：[系统架构](architecture/system.md)
- 前端路由/UI 行为：[前端架构](architecture/frontend.md)
- 后端 API/服务/运行期行为：[后端架构](architecture/backend.md)
- 产品和剧本包模型：[剧本与玩法领域](domain/script-gameplay.md)
- 玩家和剧本包工作流：[玩法与剧本包工作流](workflows/gameplay-and-packages.md)
- Supabase、配置、部署、测试：[数据与运维](operations/data-and-deployment.md)

已有的一手文档仍然有用：

- `/docs/ARCHITECTURE_OVERVIEW.md`：目标架构和理念。
- `/docs/API_REFERENCE.md`：REST 和 WebSocket 契约，但真实源码才是权威。
- `/docs/SCRIPT_PACKAGE_SCHEMA.md`：预期的剧本包创作 schema。
- `/docs/CONDITION_DSL_REFERENCE.md`：预期的阶段/事件条件语言。
- `/docs/FRONTEND_EXPERIENCE_DESIGN.md`：路由流和沉浸式 UX 设计。
- `/docs/EXECUTION_PLAN.md`：任务路线图和预期验收标准。
- `/doc/剧本系统设计.md`：产品/领域定位和内容边界规则。

## 本地命令

`README.md` 中记录的命令是：

```bash
make install
make dev
make dev-web
make test
```

根目录 `Makefile` 已提供常用入口：

```bash
# 同时启动后端和前端
make dev

# 只启动后端或前端
make dev-api
make dev-web

# 测试和检查
make test
make lint

# 本地 Supabase
make db-start
make db-reset
```

前端包还提供：

```bash
npm --prefix apps/web run build
npm --prefix apps/web run start
npm --prefix apps/web run lint
```

注意：`make dev` 会给前端传入 `NEXT_PUBLIC_USE_MOCK=false` 和本地 WebSocket 地址，用于验收真实后端心跳链路。

## 给后续 Agent 的变更指引

改后端前，先读[后端架构](architecture/backend.md)、[数据与运维](operations/data-and-deployment.md)，以及相关 route/service/repository 文件。大部分运行期行为现在位于服务层和仓储层，而不是 LangGraph 骨架里。

改前端前，先读[前端架构](architecture/frontend.md)。明确判断变更应该落在 Mock 玩法、真实 `api` wrapper，还是两者最终集成处。

改剧本包或内容前，先读[剧本与玩法领域](domain/script-gameplay.md)、`/docs/SCRIPT_PACKAGE_SCHEMA.md`、`engine/core/package_loader.py` 和相关 `engine/core/package_*` 模块。当前 loader 支持上传 zip，也支持通过 `load_package_directory()` 把松散剧本包目录打包后走同一套校验流程。

依赖环境配置前，检查当前 `Makefile`、`.env.example` 和 `engine/api/config.py`；真实密钥应放在 `.env` 或部署环境中，`.env.example` 只保留占位符。
