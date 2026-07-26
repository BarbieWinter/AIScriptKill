# 后端架构

```text
┌─ OPENWIKI PAGE ──────────────────────────────────────────────────────────────┐
│ KIND      reference                                                          │
│ SCOPE     FastAPI, services, repositories, runtime                           │
│ VERIFIED  2026-07-22 @ WORKTREE                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

[Home](../quickstart.md) / [Architecture](system.md) / **Backend**

本页说明后端职责和边界；完整 wire contract 以 OpenAPI 与源码为准。

## 一览

- [LIVE] **单人 action** — REST 已进入 YAML/LangGraph 运行路径。
- [LIVE] **多人大厅** — 房间、邀请、选角、准备和启动已接线。
- [LIVE] **持久命令基础** — receipt 和 stale recovery 已实现；`GET /sessions/{id}/events`
  page 当前只对 `legacy_single` 会话开放，多人客户端仍用快照 polling。
- [LIVE] **Slim M2 gameplay** — reducer、持久命令、HTTP 快照与复盘已接线。
- [LEGACY] **WebSocket** — 公开端点只有未认证的 ping/pong。
- [SECURITY] **数据访问** — 浏览器只经 FastAPI 读取白名单投影。

## 分层

```text
route
  -> service
     -> repository
        -> PostgreSQL / frozen package / checkpoint

single-player action
  -> LangGraphRuntimeActionExecutor
  -> ScriptEngine

multiplayer gameplay
  -> durable room command coordinator
  -> pure reducer
  -> canonical GameStateV2 + public event
  -> participant-safe snapshot/review
```

- `engine/api/`：路由、schema、认证依赖、中间件和错误映射。
- `engine/services/`：用例、事务协调、授权和响应投影。
- `engine/repositories/`：查询与写入，不拥有产品规则。
- `engine/core/`：剧本加载、条件、StateGraph、多人成熟度无关的纯逻辑。
- `engine/contracts/multiplayer_v1/`：严格、版本化的多人 wire/domain contract。

## API 边界

### Session 与 package

- `engine/api/routes/sessions.py`：创建、读取、资源查询、多人房间和命令。
- `engine/api/routes/actions.py`：单人 action 与最终提交。
- `engine/api/routes/packages.py`：管理员导入、发布和玩家安全详情。
- `engine/api/websocket/handler.py`：有界心跳，不是 gameplay transport。

不要在 OpenWiki 手抄完整 endpoint 清单。新增或修改接口后，应同时检查：

```text
route -> request/response model -> service -> OpenAPI test -> browser client
```

### 多人命令

`POST /api/v1/sessions/{session_id}/commands` 使用统一的
`execute_room_command()` 执行大厅与 Slim M2 gameplay 命令：

- 大厅：选角、取消选角、准备和启动。
- 阶段：确认阅读、讨论消息、结束确认/撤销和显式推进。
- 结算：秘密提交、共同选择和协作提示。
- 恢复：`room.resync` 是不推进 revision 的无变更命令。

每条命令都从 verified JWT principal 推导 actor membership；客户端不能提交
`member_id`、`character_id` 或 audience。

### 场景 Presence

`PUT /api/v1/sessions/{session_id}/scene-presence` 只接受 `x`、`y`、`facing` 和
`moving`。服务端从 verified anonymous JWT 与 joined/required membership 推导成员，
在 `room_members` 上替换该成员的 latest pose，并使用数据库时间。presence 不修改
`GameStateV2`、room revision、event head、receipt、outbox 或冻结 package。

participant-safe snapshot 只把 15 秒内的完整 pose 投影为 online；过期或不完整位置以
`scene_online=false` 和 null 坐标 fail closed。快照不返回 principal、更新时间或历史轨迹。
该位置只用于双方同场展示，不是碰撞、剧情推进或服务端移动权威。

## 多人持久化

### 房间与冻结包

创建房间时，服务会锁定已发布 package，编码 immutable runtime snapshot，保存
payload、version 和 SHA-256。历史房间必须从该快照恢复，不能回退到后来发布的包。

```text
published package
  -> encode immutable snapshot
  -> room row + host + reservation
  -> decode on room access
```

### Receipt、event 与 outbox

持久命令基础已包含：

- 全局 `command_id` 身份和 tombstone 约束。
- request hash、processing lease、attempt 和终态 receipt。
- stale processing reclaim 与稳定 replay。
- 有序 `session_events` 和 participant-safe snapshot page。
- 与成功事务一起写入的 `room_outbox` 记录。
- `SKIP LOCKED` batch publisher、重试次数和下次可用时间。

[CAUTION] outbox publisher 是可调用服务，不代表已有常驻 worker、broker 或
WebSocket fan-out。Slim M1 也不依赖这些设施。

## 运行时

### 单人

`LangGraphRuntimeActionExecutor` 在 advisory lock 内重读 session，从规范化已发布
package 重建运行时，恢复 checkpoint，再执行 StateGraph。checkpoint 与业务投影
分开提交；message id 和 discovery upsert 用于幂等重放。

### 多人

`engine/core/multiplayer_state_machine.py` 提供：

- read barrier、discussion close 和 settlement reducer。
- 同步进入下一阶段并解锁角色章节。
- final judgment 通过已校验 `ending_by_outcome` 解析 authored ending 的完成操作。
- `GameStateV2` completed/revealed outcome/ending 存在性不变量；outcome 与 ending ID 可不同。

`engine/core/multiplayer_review.py` 只投影 completed room，要求成员身份、匹配的
final definition 和解码后的冻结包。`GET /sessions/{id}/review` 先探测多人房间，
仅对非多人 session 回退 legacy review。

## 剧本包导入

```text
zip or directory
  -> package_loader
  -> strict YAML / Markdown
  -> reference and asset validation
  -> normalized records
  -> package repository
```

声明 multiplayer 的剧本版本通过一个不可变 playability 结果统一校验玩家范围、角色章节覆盖、材料引用、阶段 effect、终局拓扑，以及 final outcome 到 authored ending 的显式完整映射。loader、发布、房间创建和冻结版本快照解码消费同一结果；失败必须在写入或开局前阻断，而不是在运行期猜测修复。

## 边界

- **包含：** API、授权、service/repository、runtime 和持久命令职责。
- **不包含：** 完整 schema 枚举、迁移清单或未来路线图。
- [SECURITY] **复盘** — 不得返回 canonical state、完整冻结包或私有 submission。
- [CAUTION] **状态** — event/outbox 基础不能被描述成完整 event-sourcing 平台。

## 变更导航

| 修改目标 | 首先查看 | 验证入口 |
|---|---|---|
| Session API | `engine/api/routes/sessions.py` | `test_api_contracts.py` |
| 多人 room/gameplay | `multiplayer_room_service.py`, `multiplayer_gameplay_service.py` | gameplay service + durable HTTP tests |
| 持久命令 | `session_command_repository.py` | `test_multiplayer_command_http.py` |
| 多人 reducer | `multiplayer_state_machine.py` | offline state-machine tests |
| Package loader | `package_loader.py` | `test_multiplayer_package_loader.py` |

## 权威来源

- **运行时：** `engine/api/`, `engine/services/`, `engine/repositories/`。
- **领域：** `engine/core/`, `engine/contracts/multiplayer_v1/`。
- **数据：** `supabase/migrations/`, `engine/db/tables.py`。
- **设计：** `docs/ARCHITECTURE_OVERVIEW.md` 仅描述总体意图。

---

[Previous: System](system.md) · [Home](../quickstart.md) ·
[Next: Frontend](frontend.md)
