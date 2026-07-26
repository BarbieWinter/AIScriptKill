# OpenWiki 控制台

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│ AISCRIPTKILL :: OPENWIKI                                                     │
├──────────────────────────────────────────────────────────────────────────────┤
│ PRODUCT   Fixed-script immersive mystery engine                              │
│ PRIORITY  Two-player product validation                                      │
│ HOME      openwiki/quickstart.md                                             │
│ STATUS    Current implementation, not roadmap completion                     │
└──────────────────────────────────────────────────────────────────────────────┘
```

`[LIVE]` 已接入真实运行路径。 `[PARTIAL]` 仅完成部分链路。
`[MOCK]` 浏览器内演示。 `[PLANNED]` 尚未实现。

## 导航

- [系统架构](architecture/system.md)
- [后端架构](architecture/backend.md)
- [前端架构](architecture/frontend.md)
- [剧本与玩法](domain/script-gameplay.md)
- [数据与运维](operations/data-and-deployment.md)

## 当前判定

| 切片 | 状态 | 可交互边界 |
|---|---|---|
| 单人 Mock | `[MOCK]` | 浏览器内完整演示，刷新会重置 |
| 单人 Live | `[LIVE]` | REST、YAML、LangGraph 与持久化 |
| 双人大厅 | `[LIVE]` | 创建、邀请、选角、准备、开始 |
| Slim M2 | `[LIVE]` | 双浏览器 HTTP polling 通关与 completed-only 复盘 |
| AI DM / gameplay WS | `[PLANNED]` | 不作为 Slim M2 依赖 |

[PASS] Slim M2 已由 route-mocked 双 context、PostgreSQL ASGI 全流程和真实本地
Supabase/FastAPI/Next 双匿名身份三层验证。当前玩法刻意使用 HTTP polling；这不表示
WebSocket、presence、地图移动或公共 AI DM 已实现。

## 事实来源

```text
priority  source
--------  ---------------------------------------------------------------------
1         executable source + migrations + tests
2         CONTEXT.md domain invariants
3         script-packages/* authored content
4         OpenWiki current implementation guides
5         docs/* design intent and long-form project design
```

- 实现状态必须由源码和测试验证，不能由路线图勾选项推断。
- `docs/` 保存项目级总设计，不保存 ADR 或阶段验收报告。
- OpenWiki 保存当前结构、边界、工作流和运维入口，不复制完整 API/schema。
- `.last-update.json` 是外部生成器状态，不是页面新鲜度证明。

## 快速启动

```bash
make install
make dev
```

`make dev` 和 `make dev-web` 默认使用前端 Mock：

```bash
make dev-web
```

需要真实 API 联调时显式关闭 Mock：

```bash
NEXT_PUBLIC_USE_MOCK=false make dev
# 或
NEXT_PUBLIC_USE_MOCK=false make dev-web
```

本地数据库与验证入口：

```bash
make db-start
make db-reset
make test
make lint
make typecheck-api
```

[CAUTION] `make db-reset` 会执行旧开发 seed。当前 Live 剧本仍应从
`script-packages/` 导入并发布。

## 变更入口

| 任务 | 先读 | 主要源码 |
|---|---|---|
| 系统边界 | [系统架构](architecture/system.md) | `engine/`, `apps/web/` |
| API / runtime | [后端](architecture/backend.md) | `engine/api`, `engine/services` |
| 页面 / Mock | [前端架构](architecture/frontend.md) | `apps/web` |
| 剧本内容 | [剧本与玩法](domain/script-gameplay.md) | `script-packages` |
| 数据 / 启动 | [运维](operations/data-and-deployment.md) | `supabase`, `Makefile` |

## TUI 排版契约

OpenWiki 页面统一遵循：

- 正文显示宽度不超过 88 列；长路径和命令可以独占一行。
- 每页只有一个 H1，只使用 H2/H3 组织内容。
- 80 列闭合框只放在 `text` fence 中，框内优先使用 ASCII。
- 状态只使用 `[LIVE]`、`[PARTIAL]`、`[MOCK]`、`[LEGACY]`、
  `[PLANNED]`。
- 验证只使用 `[PASS]`、`[NOT-RUN]`、`[BLOCKED]`。
- 风险只使用 `[SECURITY]` 和 `[CAUTION]`。
- 表格仅用于 2 至 4 列短对照；流程、命令和文件树使用代码块。
- 导航链接必须位于代码块之外，确保终端可点击。
