# 数据与运维

```text
┌─ OPENWIKI PAGE ──────────────────────────────────────────────────────────────┐
│ KIND      runbook                                                            │
│ SCOPE     Configuration, Postgres, validation and local operation            │
│ VERIFIED  2026-07-22 @ WORKTREE                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

[Home](../quickstart.md) / **Operations** / **Data and Deployment**

本页维护本地启动、凭据、数据库和验证边界，不保存阶段验收报告。

## 一览

- [LIVE] **FastAPI data path** — async SQLAlchemy 访问 Supabase/Postgres。
- [LIVE] **Package persistence** — 规范化 package 与 runtime 表已接入。
- [LIVE] **Durable commands** — receipt、events、tombstones 和 outbox 表已实现。
- [LIVE] **Room event relay** — 独立 worker、租约恢复、退避/poison、NOTIFY adapter 与健康面已实现。
- [LIVE] **真实多人验证** — durable PostgreSQL 与双匿名浏览器 live gate 已接入。
- [SECURITY] **浏览器访问** — 只允许经 FastAPI，不直接读写底层表。

## 环境配置

配置源是项目根 `.env` 和进程环境。`.env.example` 只能保存占位符。

| 范围 | 主要变量 | 说明 |
|---|---|---|
| Supabase | `SUPABASE_URL`, keys | secret key 仅服务端使用 |
| Database | `DATABASE_URL`, pooler | pooler 存在时优先 |
| Frontend | `NEXT_PUBLIC_*` | 只能放公开值 |
| Rollout | `MULTIPLAYER_V1`, `ROOM_EVENTS_V1` | API 与 room-event relay 独立启用 |
| Relay | `ROOM_EVENT_RELAY_*`, `ROOM_EVENT_NOTIFY_CHANNEL` | 租约、重试、停机和 NOTIFY channel |
| RAG | `RAG_*`, `DASHSCOPE_*` | embedding 维度 1024 |
| NPC | `NPC_*`, `OPENAI_*` | 配置不全时安全 fallback |

`make dev*` 会从根 `.env` 补充公开 Supabase 值，但 Mock 开关由 Make 默认值覆盖：

```text
make dev / make dev-web                  -> NEXT_PUBLIC_USE_MOCK=true
NEXT_PUBLIC_USE_MOCK=false make dev      -> Live frontend
```

## 常用命令

```bash
make install
make verify-dev-tools

make db-start
make db-reset

make dev
make dev-api
make dev-relay
make dev-web

make test
make lint
make typecheck-api
```

持久命令与 room-event relay 数据库 lane：

```bash
make test-durable-commands
make test-room-event-relay
```

浏览器验证：

```bash
make test-mp2-contract
make test-mp2-live
```

`test-mp2-contract` 使用 route-mocked Supabase/HTTP，覆盖双 context 页面契约。
`test-mp2-live` 要求真实 Supabase Auth、已迁移 PostgreSQL、已发布
`mp1-two-player`、FastAPI 和 Next.js 全部可达；它从创建房间通关到 completed
review，且断言没有 gameplay WebSocket。

[PASS] Slim M2 当前有三层证据：

1. 服务级真实冻结包 reducer 与 participant projector。
2. ASGI + PostgreSQL durable command 全流程。
3. 两个真实 Supabase anonymous identity 的 live browser 全流程。

[CAUTION] `make db-reset` 后必须通过管理员 package import API 重新发布真实包。
本地导入建议显式使用 `RAG_EMBEDDING_PROVIDER=deterministic`，避免 gameplay 验收
依赖外部 embedding provider。

## 数据库边界

迁移位于 `supabase/migrations/`，SQLAlchemy metadata 位于
`engine/db/tables.py`。修改表结构时必须同步两处以及 required-table health inventory。

主要数据族：

- 规范化剧本 package、stage、character、chapter、clue、evidence、scene、media。
- service-only ending、DM guide、RAG knowledge 与角色章节。
- 单人 session、checkpoint、pending writes、chat、discovery 和 review。
- 多人 room member、assignment、invite、required member 和 principal reservation。
- durable command identity、receipt、event、tombstone 和 room outbox。

[CAUTION] 不在 OpenWiki 复制逐迁移清单。实际顺序和约束以迁移文件为准。

## 权限与防剧透

[SECURITY] `anon` 和 `authenticated` 浏览器角色不应拥有底层业务表权限。

```text
browser
  -> FastAPI auth
  -> session / membership authorization
  -> stage + role + discovery filtering
  -> participant-safe response
```

- 管理操作只信任 Supabase `app_metadata` 中的管理员角色。
- 多人必须使用 verified anonymous JWT，并通过 principal → membership 授权。
- `service_role`、数据库 URL 和 provider secret 不得进入浏览器 bundle。
- package snapshot、DM truth、其他成员私态和 submission 不得直接序列化。

## 事务与恢复

### 单人

```text
advisory lock transaction
  + checkpoint transaction
  + request projection transaction
```

三者不是一次原子提交。恢复依靠 checkpoint、稳定 message identity 和单调 discovery
合并，不能描述成完整 event sourcing。

### 多人命令

成功终态可在同一事务中更新 room、receipt、event 和 outbox。stale processing 通过
lease/attempt 恢复；同一 `command_id` 绑定稳定 request hash 和 session identity。

room-event relay 以独立 ASGI 进程运行；claim 事务提交后才调用 transport，活跃租约以 token
fencing，失败按上限退避并在阈值后进入 poison。`/health/ready` 暴露聚合 queue lag、累计
retry attempts 与 poison 状态，部署入口见 `docker-compose.yml` 的 `room-event-relay` 服务。
应用优先在配置期限内 graceful shutdown；Compose 在 15 秒后强制终止，保证停机有界。

[CAUTION] PostgreSQL NOTIFY 可能重复或在 listener 离线时丢失，因此只作为稳定事件引用的低延迟
唤醒；下游必须从持久事件读取并按 `event_id` 幂等。认证 WebSocket fan-out/replay 仍属后续工作。

## 本地数据注意事项

- `supabase/seed/dev_seed.sql` 是旧内容，不能覆盖当前 `script-packages/`。
- `make db-reset` 后应重新导入并发布需要验证的真实 package。
- 修改 Supabase Auth 配置后，应重启本地 Supabase。
- `/health/db` 要求 required tables 已完成迁移。
- Docker/Supabase 不可用时，数据库测试的 skip 不能写成 PASS。

### 双人候选发布门禁

`make test-t08-candidate` 是严格双人候选的本地收敛入口。它会清空并迁移本地
Supabase（不运行旧 seed），先拒绝任何 staged、unstaged 或 untracked 工作树变更，以及
候选提交中的冲突标记与空白错误，再对同一 clean checkout 执行静态分析、生产构建、
完整后端与数据库测试和 route-mocked 浏览器测试，
再启动 FastAPI 与 production Next，通过真实管理员 JWT
调用 package 导入 API，最后运行双匿名身份 Live 通关。候选差异默认以本地 `main` 的
merge-base 为基线；非标准基线必须显式设置 `T08_CANDIDATE_BASE_REF`。

该门禁具有破坏性，只能指向可丢弃的本地数据库。任一 migration、权限、package asset、
authoring capability、隐私、reservation、终局网络生命周期或玩家旅程缺口都必须使总命令
失败；不能通过预置 SQL 或直接 repository 写入绕过管理发布路径。

## 验证口径

| 标记 | 含义 |
|---|---|
| `[PASS]` | 命名的命令或 gate 已实际成功执行 |
| `[NOT-RUN]` | 没有执行，不作结论 |
| `[BLOCKED]` | 所需环境不可用或 gate 被阻止 |

不要创建 `docs/reports/` 保存每轮输出。长期有效的边界更新到 OpenWiki；一次性
命令结果留在提交、CI 或会话记录中。

## 边界

- **包含：** 配置、命令、数据族、权限、事务和验证口径。
- **不包含：** 逐迁移说明、临时测试报告或部署供应商教程。
- [SECURITY] **凭据** — 真实 secret 只放 `.env` 或部署环境。
- [CAUTION] **Mock** — 默认 Mock 是开发安全默认值，不代表 Live 已失效。

## 变更导航

| 修改目标 | 首先查看 | 验证入口 |
|---|---|---|
| 环境变量 | `engine/api/config.py` | config tests |
| 启动行为 | `Makefile`, `.env.example` | `make -n dev` |
| 数据表 | `supabase/migrations/` | migration tests |
| 浏览器权限 | data-access migrations | privilege test |
| Outbox | `engine/services/room_outbox.py` | command HTTP tests |

## 权威来源

- **配置：** `engine/api/config.py`, `.env.example`, `Makefile`。
- **数据库：** `supabase/migrations/`, `engine/db/tables.py`。
- **验证：** `engine/tests/`, `apps/web/e2e/`。
- **部署：** `docker-compose.yml` 和 Dockerfiles。

---

[Previous: Gameplay](../domain/script-gameplay.md) · [Home](../quickstart.md) ·
[Next: System](../architecture/system.md)
