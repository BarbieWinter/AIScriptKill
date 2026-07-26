# 系统架构

[← OpenWiki](../quickstart.md) · [后端](backend.md) · [前端](frontend.md) ·
[领域](../domain/script-gameplay.md) · [运维](../operations/data-and-deployment.md)

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│ SYSTEM :: CURRENT IMPLEMENTATION                                             │
├──────────────────────────────────────────────────────────────────────────────┤
│ FRONTEND   Next.js 15 / React 19                                             │
│ API        FastAPI / strict participant projections                          │
│ RUNTIME    LangGraph single-player + pure multiplayer reducer                │
│ DATA       Supabase Postgres / immutable multiplayer package snapshot        │
│ DELIVERY   HTTP active; gameplay WebSocket not implemented                   │
└──────────────────────────────────────────────────────────────────────────────┘
```

## 总览

```text
Browser
  |
  +-- single-player Mock ------------------------> in-memory Mock engine
  |
  +-- single-player Live -- HTTP ---------------> FastAPI
  |                                                |
  |                                                +-- package/runtime services
  |                                                +-- LangGraph + checkpoint
  |                                                +-- Postgres projections
  |
  +-- multiplayer -- HTTP polling --------------> room/gameplay service
                                                   |
                                                   +-- frozen package snapshot
                                                   +-- deterministic reducer
                                                   +-- durable receipt/events
                                                   +-- participant-safe snapshot/review
```

## 能力状态

| 能力 | 状态 | 当前边界 |
|---|---|---|
| 单人 Mock UI | `[MOCK]` | 本地场景、聊天、线索、提交和复盘 |
| 单人 Live UI | `[LIVE]` | Session API、YAML presentation、LangGraph action |
| 双人大厅 | `[LIVE]` | 匿名身份、邀请、选角、准备、启动 |
| Durable command | `[LIVE]` | receipt、replay、event page、stale recovery |
| Room outbox | `[PARTIAL]` | 表、事务写入和 publisher；无常驻 worker |
| Slim M2 双人 gameplay | `[LIVE]` | HTTP polling、私有章节、讨论、结算、完成复盘 |
| Gameplay WebSocket | `[PLANNED]` | 当前公开 WS 只有 legacy ping/pong |
| 公共 AI DM | `[PLANNED]` | flag 存在，未接多人运行时 |

## 权威边界

### 内容

- `script-packages/snow-village`：单人 Live 垂直切片。
- `script-packages/mp1-two-player`：Slim M3 真人试玩候选双人包。
- Mock 数据仅用于前端体验，不覆盖 authored package。

### 状态

- 单人 Live continuation 优先来自 LangGraph checkpoint。
- `game_sessions.state` 是查询投影，不是完整历史。
- 多人 `GameStateV2` 是 canonical materialized state。
- 当前多人状态只保存当前阶段，不伪造已离开阶段的私有票型历史。

### 隐私

[SECURITY] 浏览器不能直接读取剧本私密表、RAG、DM truth 或其他玩家状态。

- 单人资源由 FastAPI 按 session、角色、阶段和 discovery 投影。
- 多人大厅由 verified anonymous principal 映射 membership。
- participant snapshot 只包含请求者自己的 `private_state`。
- completed review 只能读取房间冻结包，并保持 authored reveal 粒度。

## 关键数据流

### 单人 Live

```text
POST /sessions/{id}/actions
  -> session_service.perform_action
  -> LangGraphRuntimeActionExecutor
  -> advisory lock
  -> frozen published package reconstruction
  -> checkpoint restore/bootstrap
  -> YAML StateGraph action
  -> checkpoint commit
  -> session/chat/discovery projection commit
```

[CAUTION] advisory lock、checkpoint 和业务投影并非同一数据库事务。幂等投影
降低重放风险，但不等于原子 event-sourcing 系统。

### 多人 HTTP gameplay

```text
anonymous JWT
  -> room membership
  -> lobby or gameplay snapshot
  -> revision + durable receipt coordinator
  -> deterministic reducer
  -> GameStateV2 + ordered public event
  -> participant-safe snapshot / completed review
```

聊天事件推进 `event_head_sequence` 但不推进 room revision；状态 mutation 同时推进
revision 和 event sequence。秘密结算在全部提交前只返回提交成员列表和自己的选择。
正常完成时释放 principal reservation，复盘仍要求原 room membership。

## Slim M2 验证边界

[PASS] 当前切片已经验证：

- 两名真实匿名玩家创建、邀请、选角、准备和启动。
- 每人只收到自己的逐阶段章节，公共材料按节点揭晓。
- 只追加公开讨论、结束确认/撤销和秘密投票统一揭晓。
- 显式同步推进、共同最终判断、authored ending 和 completed-only review。
- durable receipt 重放、revision 冲突刷新、完成时 reservation 释放。

明确推迟：

- gameplay WebSocket、presence、Redis 和 outbox 常驻 worker。
- 共同沉浸地图、远端 avatar pose 和跨日浏览器恢复验收。
- 未完成对局结束 UI、公共 AI DM、正式负载与多实例稳定性。
- 真实玩家趣味性验证；技术通关不等于内容已经有趣。

## 路由归属

| 路由族 | 所有者 | 状态 |
|---|---|---|
| `/library`, `/play/...` | 单人前端 | `[LIVE]` / `[MOCK]` |
| `/multiplayer`, `/invite/...` | 多人大厅 | `[LIVE]` |
| `/play/{room}/lobby` | 多人大厅 | `[LIVE]` |
| `/demo/*` | 兼容重定向 | `[LEGACY]` |
| `/api/v1/sessions/*` | FastAPI session surface | `[LIVE]` |
| `/api/v1/ws/*` | 心跳端点 | `[LEGACY]` |

完整路由与模型以 `engine/api/routes/`、`apps/web/app/` 和生成的 OpenAPI 为准，
不在本页复制枚举。

## 刻意不做

- 不为 Slim M1 引入通用剧情 branch graph。
- 不用 WebSocket 代替尚未验证的 HTTP polling 产品体验。
- 不从私有 submission 反推更详细的历史 reveal。
- 不让 AI 决定结局、阶段推进、解锁或 canonical state patch。
- 不把 outbox 表的存在描述成已部署的异步消息平台。
