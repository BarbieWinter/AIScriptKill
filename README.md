# AI Script Kill — 多人在线剧本杀执行平台

由固定剧本控制流程、真人玩家完成阅读讨论与推理、AI 受限辅助主持的在线剧本杀系统。

- **玩家**进入同一房间，各自持有私有角色剧本，通过公开讨论与信息不对称推进故事。
- **YAML 剧本包**拥有内容创作权：阶段、章节、公共材料、结算与结局。
- **程序**拥有执行权：权限、状态机、幂等、持久化、同步与恢复。
- **AI DM**（规划中）只在剧本声明的节点提供受限主持，不改状态、不替玩家下结论。

完整产品边界与当前完成度见
[`docs/PRODUCT_DIRECTION_AND_IMPLEMENTATION_STATUS.md`](docs/PRODUCT_DIRECTION_AND_IMPLEMENTATION_STATUS.md)（项目状态权威文档）。

## 当前可玩内容

| 剧本包 | 模式 | 状态 |
|---|---|---|
| `mp1-two-player`《两份口供》 | 双人多人 | 可从建房、邀请、选角、读本、讨论、秘密投票走到终局与复盘（HTTP 命令 + 2 秒快照轮询） |
| `snow-village`《雪落之前：后门的脚印》 | 单人 | 旧方向的单人垂直切片，保留为回归基线 |

前端入口：

- `/multiplayer` — 创建双人房间（固定使用 `mp1-two-player`）；受邀方通过 `/invite/{token}` 加入。
- `/library` — 单人剧本库与单人流程。
- `/demo/*` — 旧演示路由，仅重定向，不再是产品入口。

已知边界（详见状态权威文档）：多人传输是 HTTP 轮询而非 WebSocket 实时流；流程仍是固定
READ → DISCUSS → SETTLE → REVEAL 四相；AI DM 尚未实现；旧地图搜证依赖尚未清理完成。

## 项目结构

```text
AIScriptKill/
├── engine/               # Python 后端（FastAPI + LangGraph + 多人 reducer）
│   ├── core/             # 引擎内核（剧本包加载/条件评估/多人状态机）
│   ├── contracts/        # 多人 v1 严格契约（state/commands/authoring/reviews）
│   ├── agents/           # AI Agent（DM/NPC/Guard/Hint；多为占位或旧方向）
│   ├── rag/              # RAG 检索系统（冻结，后续服务公共 DM）
│   ├── services/         # 业务服务（房间/玩法/命令/复盘）
│   ├── repositories/     # 数据读写
│   ├── api/              # FastAPI 网关
│   └── tests/            # 测试
├── apps/web/             # Next.js 15 前端（单人壳 + 多人大厅与游戏壳）
├── script-packages/
│   ├── mp1-two-player/   # 《两份口供》双人剧本包
│   └── snow-village/     # 《雪落之前》单人剧本包
├── supabase/             # 数据库迁移与旧开发种子
├── docs/                 # 项目级设计与状态文档（见 docs/README.md 索引）
└── openwiki/             # 当前实现结构、边界与运维入口
```

## 快速开始

```bash
# 安装依赖并验证开发工具
make install
make verify-dev-tools

# 后端测试、静态检查与严格类型检查
make test
make lint-api
make typecheck-api

# 启动并重置本地 Supabase
make db-start
make db-reset

# 同时启动后端和前端（默认前端 Mock）
make dev

# 真实 API 联调时显式关闭 Mock
NEXT_PUBLIC_USE_MOCK=false make dev
```

`make dev` 会让 Next.js 将 `/api/*` 代理到 `http://localhost:8000`。

**数据库重置后必须重新导入剧本包**：`supabase/seed/dev_seed.sql` 是旧阶段种子，不能作为
当前内容来源。需通过管理员 `POST /api/v1/packages?publish=true` 将
`script-packages/mp1-two-player/`（以及需要单人回归时的 `snow-village/`）归档导入并发布，
才能创建房间或 Live 会话。

其他验证命令：

```bash
make test-durable-commands       # 持久命令、幂等与双人 HTTP 通关（需数据库）
make test-checkpoint-recovery    # checkpoint 强杀恢复（需数据库）
make test-mp2-live               # 真实 Supabase/FastAPI/Next 双人完整通关
make test-t08-candidate          # 从空库执行完整双人候选发布门禁
make test-database-privileges    # 数据库权限门禁
make lint-web
```

`make test-t08-candidate` 是破坏性的本地发布门禁：它使用 `--no-seed` 重置本地
Supabase，先检查候选提交与工作树的冲突标记/空白错误，再执行完整后端、数据库、静态分析、生产构建和 route-mocked 浏览器测试，随后
通过真实管理员 API 发布标准双人包并运行双身份 Live 旅程。不要对包含需保留数据的本地
数据库执行该命令。

## 文档导航

- [`docs/README.md`](docs/README.md) — **docs 索引**：各文档的定位、权威性与阅读顺序
- [`docs/PRODUCT_DIRECTION_AND_IMPLEMENTATION_STATUS.md`](docs/PRODUCT_DIRECTION_AND_IMPLEMENTATION_STATUS.md) — 产品方向与实现状态（**冲突时以此为准**）
- [`CONTEXT.md`](CONTEXT.md) — 领域语境与术语表
- [`openwiki/quickstart.md`](openwiki/quickstart.md) — 当前实现结构、工作流与变更入口
