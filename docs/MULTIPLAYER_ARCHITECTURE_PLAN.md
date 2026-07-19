# 多人联机架构与执行计划

> 状态：`APPROVED · MP-0 COMPLETE`
> 目标：`Multiplayer v1`
> 玩家：首版严格 2 人，底层按玩家集合建模
> 主持：公共 AI DM
> 更新：`2026-07-17`
>
> 本文同时描述“当前实现”和“目标架构”。未标记为 `[x]` 的任务均不是当前能力；
> 当前实现事实以源码、[MP-0 基线报告](reports/mp-0-baseline-2026-07-17-bae4a55.md)
> 和第 4 节的权威矩阵为准。

配套领域语言见 [`../CONTEXT.md`](../CONTEXT.md)。关键边界见：

- [`ADR-0001`](adr/0001-human-multiplayer-with-public-ai-dm.md)
- [`ADR-0002`](adr/0002-shared-stage-not-search-game.md)
- [`ADR-0003`](adr/0003-yaml-authority-for-stage-settlement.md)

---

## 0. 一屏说明

```text
┌────────────────────────────────────────────────────────────────────┐
│ AIScriptKill · Multiplayer v1                                    │
├────────────────────────────────────────────────────────────────────┤
│ 核心玩法   私有读本 → 公共讨论 → YAML 结算 → 同步推进            │
│ 玩家规模   首版 2 名真人；底层不写死两人                         │
│ AI 角色    公共主持、规则解释、三级提示；不做裁判或 NPC          │
│ 地图角色   共同沉浸舞台；不是分头探索或自由搜证                  │
│ 玩法权威   YAML + Deterministic Runtime + LangGraph              │
│ 数据权威   PostgreSQL                                             │
│ 实时通道   WebSocket；Redis 只保存可重建临时状态                 │
└────────────────────────────────────────────────────────────────────┘
```

```text
[x] 单人 YAML 垂直切片     [x] T-2.4 RAG
[x] Live Demo / Session    [ ] 多人阶段语义
[ ] 房间 / 身份 / 选角     [ ] 命令 / 事件 / 断线恢复
[ ] 双浏览器可玩闭环       [ ] 公共 AI DM
```

### 先回答最容易混淆的问题

| 问题 | 答案 |
|---|---|
| 先做状态机还是 WebSocket？ | 先做无网络的多人阶段状态机。 |
| T-2.4 RAG 是否废弃？ | 不废弃；冻结 NPC 扩展，后续服务公共 DM。 |
| 玩家是否分头走地图找线索？ | 否。地图是共同舞台，材料由 YAML 发放。 |
| AI DM 是否决定任务完成？ | 否。阶段流程和结算由 YAML 决定。 |
| AI DM 是否可以私聊？ | 否。所有 DM 发言都对全房间公开。 |
| AI DM 是否实时扮演 NPC？ | 首版不做。 |
| 玩家能否撒谎？ | 可以；DM 不揭穿角色陈述。 |
| 掉线后是否丢局？ | 不丢；原身份可以恢复同一房间。 |

---

## 1. 产品循环

### 1.1 一局游戏

```text
创建房间
  → 分享邀请链接
  → 第二名玩家加入
  → 各自自由选角
  → 全员准备
  → 开始对局
  → 重复执行多个阶段
  → 最终结算
  → 正常完成后开放完整复盘
```

首版加入规则：

- 使用无感匿名身份，不要求邮箱或密码。
- 同一匿名身份只能参与一局未完成游戏。
- 匿名身份绑定当前浏览器；清除数据或换设备后，首版不能认领旧角色。
- 房间可跨天继续；所有玩家离线时不推进。
- 通关后允许创建新房间重玩，但明确提示玩家已经知道真相。

### 1.2 一个阶段

```text
┌──────────────┐
│ stage.enter  │
└──────┬───────┘
       ▼
┌──────────────────────────────────────┐
│ READ · 读本期                       │
│ 每名玩家只读自己的当前角色章节       │
│ 阅读完成在讨论开始前可以撤销          │
└──────┬───────────────────────────────┘
       │ all required players read
       ▼
┌──────────────────────────────────────┐
│ DISCUSS · 讨论期                    │
│ 唯一公共文字聊天                     │
│ 玩家可以陈述、隐瞒、误导或撒谎       │
│ 全员同意后结束讨论                   │
└──────┬───────────────────────────────┘
       │ all players agree to close
       ▼
┌──────────────────────────────────────┐
│ SETTLE · 结算期                     │
│ none / secret_vote / shared_choice  │
│ / final_judgment                    │
└──────┬───────────────────────────────┘
       │ settlement complete
       ▼
┌──────────────────────────────────────┐
│ REVEAL · 揭晓与同步推进             │
│ 发放材料、公开允许的结果、解锁下一章 │
└──────────────────────────────────────┘
```

### 1.3 读本规则

- 角色章节按阶段逐章解锁，不能提前阅读后续章节。
- 每个角色每章末尾可以有自己的行动目标。
- 角色任务是私有剧本文字，不是任务清单，也没有完成百分比。
- 玩家不能一键分享章节、段落或任务原文。
- 玩家可以在聊天中自行转述、隐瞒或说谎。
- 需要公开的原文必须由 YAML 定义为公共材料。
- 全员读完后才开放本阶段讨论。
- 进入讨论后仍可回看自己的已解锁章节。

### 1.4 讨论规则

- 正式交流只发生在游戏内公共文字聊天。
- 不提供玩家私聊、DM 私聊、语音或附件上传。
- 玩家消息发送后不可编辑、不可撤回。
- 全员同意结束讨论前，任何人都可以撤销自己的结束意向。
- 最后一人同意后，普通聊天锁定并进入结算。
- YAML 可以配置建议讨论时长；到时只提醒，不强制结束。
- 一名玩家掉线时，在线玩家仍可发言；阶段结算与推进暂停。

### 1.5 结算规则

每个阶段由 YAML 选择一种结算：

| 模式 | 行为 |
|---|---|
| `none` | 全员同意结束讨论后直接推进。 |
| `secret_vote` | 各自秘密提交，全部到齐后实名揭晓。 |
| `shared_choice` | 全员确认同一个共同答案。 |
| `final_judgment` | 使用 YAML 指定的最终推理模式。 |

- 秘密提交期间只能看到“某玩家已提交”，不能看到其选择。
- 默认提交后不可修改。
- 全部提交到齐后，默认实名公开票型。
- YAML 可以为特殊结算改为只公开统计或结论。
- 普通阶段结果默认记录并继续；只有 YAML 明确声明时才改变分支。
- 最终推理可以是共同答案，也可以是个人秘密投票，由 YAML 指定。
- AI DM 和房主都不能替玩家提交或修改结果。

### 1.6 公共材料

公共线索、证物、图片和固定文本由 YAML 在确定节点发放：

```text
stage_enter       进入阶段
all_players_read  全员读完
settlement_done   结算完成
outcome:<id>      出现指定结算结果
```

首版不把地图搜索作为材料入口。少量舞台交互只有在 YAML 明确要求时存在，
且属于演出动作，不构成自由搜证系统。

### 1.7 复盘与未完成对局

正常完成：

- 开放全部角色章节和秘密。
- 开放完整真相、正确答案、票型和关键聊天记录。
- 展示提示使用次数与最高等级，但首版不扣分、不改变结局。

中途结束：

- 标记为“未完成”。
- 不开放后续章节、正确答案和完整真相。
- 不允许新人或 AI 接管退出者的角色。
- 可以等待原玩家恢复，或由玩家结束房间。

---

## 2. AI DM 边界

### 2.1 定位

```text
AI DM = 公共主持 + 规则解释 + 受约束提示
AI DM ≠ 游戏裁判 + 玩家 + NPC + 剧情作者
```

DM 所有发言对全房间公开，不存在私聊。

### 2.2 发言节点

DM 默认保持安静，只在以下节点发言：

- 阶段开始、讨论开始、结算开始和结果揭晓。
- YAML 公共材料发放。
- 玩家询问规则。
- 全员同意后的剧情提示。
- 系统检测到长时间无流程进展时，询问是否需要提示。
- 玩家掉线、重连或阶段等待等系统状态变化。

DM 不逐句插话，也不代替玩家角色发言。

### 2.3 全知但受约束

DM 后台可以理解：

- 完整真相。
- 全部角色剧本与秘密。
- 当前阶段与未来阶段安排。
- 已发生的权威事件和公开聊天。
- DM-only RAG 内容。

公开输出只能使用：

- 当前阶段允许公开的事实。
- 已发放的公共材料。
- YAML 当前允许的主持文本。
- YAML 预设的当前提示等级。

DM 不揭穿玩家与私有剧本不一致的陈述，只纠正规则与已公开系统事实。

### 2.4 三级渐进提示

```text
Level 1  提醒关注方向
Level 2  指出相关公共材料
Level 3  说明下一步应讨论或检查什么
```

规则：

- 任一玩家可以发起请求。
- 每一级都必须全员同意后公开。
- 升级到下一等级时重新确认。
- Level 3 仍不能直接公布最终答案。
- YAML 没有配置提示时，DM 只能解释规则。
- 自动停滞检测只询问，不直接发提示。

### 2.5 记忆和 RAG

- DM 只记住当前对局，不建立跨房间玩家画像。
- 每次生成使用有界聊天窗口、当前对局摘要和权威事件。
- 保留 T-2.4 的分块、增量索引、混合检索和权限过滤。
- 暂停继续开发单人 NPC/RAG 功能。
- 首版不运行独立 AI NPC；非玩家人物使用 YAML 固定内容。

### 2.6 失败模式

```text
Gameplay transaction COMMIT
  → 触发 DM 生成
  → 超时 / 限流 / 无效输出 / 过期
  → 使用 YAML 固定主持文本
  → 游戏继续
```

- DM 不进入玩法事务。
- DM 不拥有 grant、transition、vote、score、ending 等写工具。
- 模型结果返回时重新检查当前阶段和事件版本。
- 过期结果丢弃。
- 完全关闭 AI 服务仍必须能够通关。

---

## 3. 地图与前端职责

### 3.1 共同沉浸舞台

```text
地图负责                              地图不负责
──────────────────────────────        ──────────────────────────────
共同场景与氛围                        分头探索
显示真人角色存在                      自由搜证
移动、镜头、碰撞和动画                决定线索权限
少量 YAML 明确的演出交互              决定阶段和结局
```

- 玩家处于同一剧情场景，可以实时看到对方角色。
- 对方位置只用于视觉插值，可丢失、可重建。
- 坐标不进入 LangGraph，不决定剧情权威。
- 刷新后可回到当前舞台的安全出生点。

### 3.2 游戏界面状态

```text
READ
  左/中央：自己的角色章节
  底部：阅读完成
  公共聊天：只读

DISCUSS
  中央：共同沉浸舞台
  侧栏：自己的章节 / 公共材料
  底部：公共文字聊天 / 结束讨论意向

SETTLE
  中央：秘密投票或共同选择
  侧栏：允许回看的角色章节 / 公共材料
  聊天：锁定

REVEAL
  中央：统一揭晓与 DM 播报
  然后所有玩家同步进入下一阶段
```

### 3.3 高频与低频状态

```text
高频临时状态                         低频权威状态
──────────────────────────────       ──────────────────────────────
本地坐标 / 速度 / 镜头               stage phase
按键 / 碰撞 / 动画                   chapter grants / read receipts
远端 avatar pose                     chat / material reveals
                                     discussion close intents
存放：React refs + RAF                settlement submissions / result
                                     存放：PostgreSQL
```

地图移动不能逐帧写 React/Zustand 或权威房间状态。

---

## 4. 权威架构

### 4.0 当前运行时事实（MP-0 基线）

目标架构实施前，现有单人运行时并不是单一状态源：

| 当前存储/模型 | 内容 | 当前用途 |
|---|---|---|
| `GameState` | LangGraph 完整 continuation | 动作与自动进程恢复权威。 |
| `SessionRuntimeState` | 有损的 REST 查询投影 | API 查询与首次图动作 bootstrap。 |
| `initial` checkpoint row | 裸 projection JSON | 创建会话时的 legacy bootstrap。 |
| versioned checkpoint row | LangGraph envelope | 完整图 checkpoint。 |
| chat/discoveries | 查询记录和外部单调进度 | 其中 6 类进度可合回图状态。 |

```text
当前动作：
route → session_service.perform_action
      → LangGraphRuntimeActionExecutor
      → 优先恢复最新 LangGraph checkpoint
      → 缺失时从 projection bootstrap
      → 合并 6 类单调进度
      → 执行 YAML/LangGraph
      → 写 checkpoint
      → 投影 game_sessions/chat/discoveries
```

当前事务仍分裂：

```text
advisory lock transaction
checkpoint saver transaction（每次自行 commit）
projection/chat/discovery request transaction
```

因此多人 Command Service 上线前，必须把 checkpoint、revision、event、outbox 和查询投影
纳入一个可恢复的提交协议。MP-0 不完成该重构，但已通过
[`ADR-0004`](adr/0004-canonical-runtime-restore-authority.md) 暂停错误的 projection-only
PATCH restore，确保公开表面只有一条真实 continuation 恢复权威。

### 4.1 目标分层（尚未实现）

```text
┌────────────────────────────────────────────────────────────────────┐
│ Browser A                         Browser B                        │
│ Private Chapter / Public Chat / Shared Stage / Participant Store  │
└───────────────┬─────────────────────────────┬──────────────────────┘
                │ HTTP Commands               │ WebSocket Events
                ▼                             ▼
┌────────────────────────────────────────────────────────────────────┐
│ FastAPI                                                           │
│ Auth → Membership → Command Service → Participant Projector       │
│                         │                         │                │
│                         ▼                         ▼                │
│              YAML / LangGraph Runtime          WS Gateway         │
└─────────────────────────┬─────────────────────────┬────────────────┘
                          │ same transaction        │ wake-up
                          ▼                         ▼
┌─────────────────────────────────────┐  ┌──────────────────────────┐
│ PostgreSQL · Source of Truth        │  │ Redis · Derived State    │
│ Room / Member / Assignment          │  │ Presence TTL             │
│ Checkpoint / Revision               │  │ Rate Limit               │
│ Chat / Submission / Event / Outbox  │  │ Node Routing / Wake-up   │
└─────────────────────────────────────┘  └──────────────────────────┘
                          │
                          ▼
┌────────────────────────────────────────────────────────────────────┐
│ AI DM Worker · Authorized Context + T-2.4 RAG + Fallback          │
└────────────────────────────────────────────────────────────────────┘
```

### 4.2 不可违反的规则

| ID | 规则 |
|---|---|
| A-01 | PostgreSQL 是唯一可恢复权威。 |
| A-02 | 一个 `game_session` 就是一间逻辑房间。 |
| A-03 | 所有权威写操作经过同一 Command Service。 |
| A-04 | actor 由 JWT → member → assignment 推导。 |
| A-05 | checkpoint、revision、event、outbox 同事务提交。 |
| A-06 | WebSocket 负责推送，不建立第二条权威写路径。 |
| A-07 | 私有投影在服务端裁剪，不把完整状态发给浏览器。 |
| A-08 | AI、Redis、socket 和 avatar pose 都不是玩法权威。 |

### 4.3 为什么不先做 WebSocket

如果先做网络层，以下未定义规则会被错误地固化：

- 读本、讨论和结算如何同步。
- 私有章节如何隔离。
- 全员确认和秘密提交如何收集。
- 掉线是否缩小必需玩家集合。
- 同时提交时如何避免重复结算。

因此第一项实现必须是无网络的多人阶段状态机测试。

---

## 5. 领域状态模型

### 5.1 `GameStateV2`

```python
class GameStateV2(TypedDict):
    state_schema_version: int
    session_id: str
    room_revision: int
    room: RoomState
    players: dict[str, PlayerState]
    private_by_member: dict[str, PrivatePlayerState]
    stage: StageRuntimeState
```

概念结构：

```text
RoomState
  status: lobby | active | completed | closed
  required_member_ids
  current_stage_id

StageRuntimeState
  phase: read | discuss | settle | reveal
  read_member_ids
  discussion_close_member_ids
  settlement
  revealed_material_ids

PrivatePlayerState
  character_id
  unlocked_chapter_ids
  settlement_draft/submission visibility
```

`required_member_ids` 在开始时锁定。掉线不会移除成员，也不会绕过全员确认。

### 5.2 Session / Room

在现有 `game_sessions` 增加：

| 字段 | 说明 |
|---|---|
| `mode` | `legacy_single` / `multiplayer_v1`。 |
| `status` | `lobby` / `active` / `completed` / `closed`。 |
| `revision` | 每次成功权威变更加 1。 |
| `event_head_sequence` | 房间事件高水位。 |
| `state_schema_version` | checkpoint 结构版本。 |
| `runtime_package_version` | 创建时固定的包版本。 |

首版不删除旧单人字段；旧 session 继续走 `legacy_single`。

### 5.3 Room Member

```text
id                  UUID PK
session_id          FK -> game_sessions
principal_id        已验证 JWT 的 sub
room_role           host | player
membership_status   joined | left | kicked
joined_at / left_at timestamp
```

约束：

- 一个 principal 同时只能有一个未完成房间成员关系。
- 同一房间一个 active membership。
- 首版房间恰好 2 名 player 才能开始。
- 底层使用成员集合，不增加 `player_a/player_b` 字段。
- connection ID、tab ID 和昵称都不是玩家身份。

### 5.4 Character Assignment

```text
UNIQUE (session_id, character_id)
UNIQUE (session_id, member_id)
```

- 玩家自由选角。
- 并发选择同一角色时只有一人成功。
- 游戏开始前可以取消并重选。
- 游戏开始后不能换角。
- 房主不能替另一名玩家选角。

### 5.5 Stage Participation

建议以 checkpoint 为权威，同时为高频查询建立事务内 projection：

```text
room_stage_participation
  session_id
  stage_id
  member_id
  read_confirmed_at
  discussion_close_confirmed_at
```

它只记录同步门槛，不记录“角色任务完成度”。

### 5.6 Settlement Submission

```text
room_settlement_submissions
  session_id
  stage_id
  settlement_id
  member_id
  encrypted_or_private_payload
  submitted_at
  revealed_at
```

- 提交前只能读取自己的 draft/提交状态。
- 其他玩家只能看到是否提交。
- 全部提交前不能读取具体选择。
- 揭晓后由 participant projector 返回 YAML 允许公开的票型。

### 5.7 Chat Message

```text
room_chat_messages
  session_id
  sequence
  sender_kind: player | dm | system
  sender_member_id
  content
  created_at
```

- 仅纯文字。
- 发送后不可编辑、不可撤回。
- 只在讨论期接收玩家消息。
- 掉线者通过 sequence 补收。
- DM 和 system 消息必须可区分。

### 5.8 Command / Event / Outbox

```text
room_commands
  UNIQUE (session_id, command_id)
  actor_member_id
  command_type
  payload_hash
  expected_revision
  result_revision
  response_json

room_events
  UNIQUE (session_id, sequence)
  audience_scope: room | member | dm
  audience_member_id
  payload_json

room_outbox
  UNIQUE (room_event_id, topic)
  attempts / available_at / published_at / last_error
```

公共与私有内容必须生成不同投影或事件，不能在浏览器隐藏完整 payload。

---

## 6. YAML 多人契约

### 6.1 包级人数

```yaml
multiplayer:
  min_players: 2
  max_players: 2
  character_assignment: required
  start_policy: all_players_ready
  duplicate_characters: false
```

- 首个 fixture 和 UI 只支持 2 人。
- schema 使用人数范围和玩家集合，为未来多人本保留扩展能力。
- 旧包没有 `multiplayer` 时按单人解释。
- 《雪乡》保持单人回归包，不直接把数字改成 2。

### 6.2 阶段结构

```yaml
id: act-1

chapters:
  detective-a: detective-a-act-1
  suspect-b: suspect-b-act-1

public_materials:
  - id: crime-scene-photo
    reveal_at: stage_enter
  - id: witness-record
    reveal_at: all_players_read
  - id: vote-followup
    reveal_at: outcome:suspect-b

discussion:
  suggested_minutes: 15
  close_policy: all_players

settlement:
  mode: secret_vote
  settlement_id: act-1-vote
  question: "你认为本阶段最可疑的人是谁？"
  options:
    - id: detective-a
      text: "侦探 A"
    - id: suspect-b
      text: "嫌疑人 B"
  reveal: named_ballots
  submission_change: forbidden
  default_effect: record_and_continue
```

### 6.3 最终推理

```yaml
settlement:
  mode: final_judgment
  settlement_id: final-judgment
  question: "你认为案件真相是什么？"
  answer_mode: shared_choice  # 或 individual_secret
  options:
    - id: conclusion-a
      text: "结论 A"
  reveal: named_ballots
  submission_change: forbidden
  default_effect: branch
```

合法模式由 schema 严格枚举，未知值在导入/发布时拒绝。

### 6.4 公共材料揭晓

首版允许：

```text
stage_enter
all_players_read
settlement_done
outcome:<declared-outcome-id>
```

MP-0 的 standalone schema 只验证上述 reveal 语法、局部 ID 唯一性和字段结构。
material、stage、outcome 与角色章节的跨文件引用完整性在 MP-1 接入 package loader 时验证；
在此之前 loader 必须继续拒绝多人字段，避免把“可解析”误写成“可发布/可执行”。

### 6.5 提示配置

```yaml
hints:
  - id: motive-chain
    levels:
      - "回顾两人的时间线是否存在交叉。"
      - "重点比较已经公开的车票和证词。"
      - "确认证词中的时间是否早于末班车。"
```

- 提示属于公共内容。
- 必须按等级顺序公开。
- 不得在最高等级直接写最终答案。
- DM 可以润色表达，不能增加 YAML 未授权事实。

### 6.6 兼容与版本

```text
legacy_single     继续使用旧单人兼容路径
multiplayer_v1    只使用 GameStateV2
```

- 引入 `state_schema_version` 和显式 upgrader。
- package/runtime version 在房间创建时固定。
- 活跃房间不读取重新发布后的新 YAML。
- 不长期双写 V1/V2 状态。

---

## 7. API 与命令

### 7.1 身份与邀请

所有 live API 要求 Bearer JWT。Supabase anonymous user 也使用合法 JWT。

```text
POST /api/v1/sessions
POST /api/v1/sessions/{id}/invites
POST /api/v1/session-invites/{token}/accept
GET  /api/v1/sessions/{id}/snapshot
POST /api/v1/sessions/{id}/commands
```

邀请链接：

- 短时有效。
- 数据库只存 hash、expiry 和 usage limit。
- 房间满员或房主撤销后失效。
- 只负责加入，不能读取游戏内容。

### 7.2 首版命令

```text
Lobby
  room.assign_character
  room.unassign_character
  room.ready
  room.start
  room.end_incomplete

Stage
  stage.confirm_read
  stage.revoke_read
  discussion.send_message
  discussion.confirm_close
  discussion.revoke_close
  settlement.submit
  settlement.confirm_shared_choice

Hint
  hint.request
  hint.confirm

Recovery
  room.resync
```

地图 pose 不属于权威 Command。

`hint.request` 与 `hint.confirm` 的 payload 都只有 `hint_id` 和 `level`；`level` 严格限制为
`1..3`。actor、session 和当前 stage 必须由服务端认证上下文推导，客户端不得提交。

`room.resync` 使用共同的 `command_id` / `expected_revision` envelope，但它是非变更型恢复请求，
payload 只有可选的 `last_event_sequence >= 0`。它必须能在客户端 revision 过期时使用，不推进
room revision，也不产生领域 mutation；MP-0 只冻结这一 wire 语义，处理器与 snapshot/replay
接线留到后续阶段。

### 7.3 Command Envelope

```json
{
  "command_id": "0190d5e7-...",
  "expected_revision": 12,
  "type": "settlement.submit",
  "payload": {
    "settlement_id": "act-1-vote",
    "option_id": "suspect-b"
  }
}
```

```json
{
  "command_id": "0190d5e7-...",
  "status": "accepted",
  "revision": 13,
  "event_sequence": 41,
  "result": {},
  "error": null,
  "replayed": false
}
```

### 7.4 单房间事务

```text
authenticate JWT
  → resolve active room member
  → advisory transaction lock(session_id)
  → verify command_id + payload_hash
  → load revision + assignment + checkpoint
  → verify expected_revision + current phase
  → execute deterministic YAML transition
  → write checkpoint + projection
  → increment revision once
  → append public/private events
  → write command result + outbox
  → COMMIT
  → publish wake-up
```

`[!]` checkpoint saver 必须复用同一 SQLAlchemy session/connection。否则多人写操作不能上线。

### 7.5 错误码

| HTTP | Code | 处理 |
|---|---|---|
| 401 | `AUTH_REQUIRED` | 重新建立匿名身份。 |
| 403 | `NOT_ROOM_MEMBER` | 禁止读取房间。 |
| 403 | `PRIVATE_CONTENT_FORBIDDEN` | 不返回资源存在性细节。 |
| 409 | `REVISION_MISMATCH` | snapshot/replay 后重新操作。 |
| 409 | `COMMAND_ID_REUSED` | 不自动重试。 |
| 409 | `PHASE_MISMATCH` | 刷新当前阶段。 |
| 409 | `SETTLEMENT_ALREADY_SUBMITTED` | 保持原提交。 |
| 422 | `INVALID_COMMAND` | 展示稳定领域错误。 |

---

## 8. WebSocket 与恢复

### 8.1 职责

```text
WebSocket 可以                       WebSocket 不可以
─────────────────────────────       ─────────────────────────────
事件推送 / 聊天推送                  绕过 Command Service
断线 replay                          把 connection 当玩家身份
heartbeat / presence                 保存唯一事件历史
非权威 avatar pose                   决定阶段、投票和材料权限
```

### 8.2 认证

```text
1. HTTPS 获取一次性短 TTL ws-ticket
2. 客户端发送 connection.hello：
   protocol_version=1、非空 ticket、可选 last_event_sequence>=0
3. 服务端校验 ticket + Origin + membership；拒绝客户端声明的
   session/member/character/audience/revision/event head
4. 服务端返回 connection.ready：
   protocol_version=1、服务端推导的 session_id/member_id、revision、event_head_sequence
5. replay cursor 后的授权事件
6. 进入 live delivery
```

长期 JWT 不放 URL query。

### 8.3 Replay 与 Snapshot

```text
reconnect(last_event_sequence)
  → 从 PostgreSQL 查询授权事件
  → 顺序补收聊天、揭晓和系统消息
  → 切换 live delivery
```

以下情况改走 participant snapshot：

- cursor 超过保留期。
- replay 数量超过上限。
- 客户端检测 gap。
- 慢消费者队列溢出。

重连后直接恢复当前游戏现场，不增加阻断式恢复页面。聊天显示未读分隔，
公共材料可标记新增，但不得泄露尚未揭晓的投票或私有章节。

### 8.4 Presence

- `(session_id, member_id) -> Set[connection]` 支持多标签页。
- 关闭一个 tab 不代表离线。
- 最后连接断开后使用 grace period 再广播 offline。
- 掉线不缩小阶段的 required member 集合。
- 在线玩家可以继续发聊天，但不能完成全员结算或推进。

### 8.5 Redis

```text
允许                               禁止
─────────────────────────────      ─────────────────────────────
presence TTL                       GameState
rate limit                         command result
node routing                       event history
new-event wake-up                  stage / vote / assignment
```

Redis 清空只能影响临时在线显示，不能丢失对局状态。

---

## 9. 数据安全与反剧透

### 9.1 服务端推导身份

```text
JWT sub
  → active room member
  → character assignment
  → participant projection
```

永远不信任客户端提交的 member、character、audience 或投票 owner。

### 9.2 私有边界

在正常揭晓前，另一名玩家不能读取：

- 角色章节原文。
- 角色任务和秘密。
- 尚未揭晓的投票选择。
- DM-only RAG 内容。
- 后续公共材料。
- 正确答案与结局条件。

这些内容不能出现在错误信息、普通日志、metrics label 或公共 WebSocket payload。

### 9.3 聊天与 DM

- 玩家输入和 YAML/RAG 文本都按不可信数据处理。
- 玩家不能通过聊天指令改变 system prompt 或要求 DM 读取他人剧本。
- DM 输出通过类型、长度、阶段、实体和剧透检查。
- 违规或模型异常使用 YAML 固定文本。
- 聊天只支持纯文字，首版不接收文件上传。

### 9.4 房主权限

房主只可以：

- 游戏开始前管理邀请和未开始成员。
- 发起技术性重新同步。
- 参与全员结束未完成对局。

房主不能：

- 查看他人角色剧本。
- 代替阅读、结束讨论或提交结算。
- 单方面推进阶段或触发剧情提示。
- 修改其他玩家的选择。

---

## 10. 执行任务卡

### 10.1 依赖图

```text
MP-0 契约基线
  └─> MP-1 阶段状态机
        └─> MP-2 房间 / 身份 / 选角
              └─> MP-3 幂等命令 / 原子事务
                    └─> MP-4 聊天 / 结算 / 事件 / 快照
                          └─> MP-5 WebSocket / Replay
                                └─> MP-6 双浏览器闭环
                                      └─> MP-7 公共 AI DM
                                            └─> MP-8 稳定性发布
```

### MP-0 · 冻结基线与契约

```text
状态    [x] COMPLETE
依赖    无
输出    ADR / schema / feature flags / baseline report
```

已完成：

- [x] 确认主计划与领域文档已真实写入项目（主计划约 1200 行）。
- [x] 记录固定 SHA 的 pre-change 基线，并分离 DB `BLOCKED` 状态。
- [x] 冻结领域语言和 4 项关键 ADR。
- [x] 确认唯一 continuation 恢复权威并暂停错误 PATCH restore。

完成项：

- [x] 定义独立 strict Multiplayer v1 状态、命令、事件与协议契约。
- [x] 定义 standalone YAML authoring contract；不接现有 loader。
- [x] 增加默认关闭的 feature flags 和契约测试。
- [x] 修正 OpenWiki/API 中与当前源码冲突的陈述。
- [x] 完成 post-change 回归并更新基线报告。

Gate：

- [x] 旧单人测试零回归（373 passed，2 个 DB probe skipped；真实 DB lane 仍因 Docker 不可用而 `BLOCKED`）。
- [x] canonical restore path 只有一个公开可达语义。
- [x] 尚未开放多人入口。

### MP-1 · 无网络多人阶段状态机

```text
状态    [ ] TODO
依赖    MP-0
输出    双人 fixture + 使用已冻结 GameStateV2 的 reducer + headless tests
```

fixture 至少包含：

- 两个真人角色和各自两章私有剧本。
- 角色任务互不公开，其中一方允许隐瞒事实。
- `stage_enter` 和 `all_players_read` 公共材料。
- 一个秘密投票阶段。
- 一个共同选择最终推理。
- 一组三级提示。

必须验证：

- [ ] 单人读完不能提前进入讨论。
- [ ] 讨论结束需要全员确认，确认可撤销。
- [ ] 投票全部到齐前不能读取他人选择。
- [ ] 揭晓后实名票型正确。
- [ ] A→B 与 B→A 的最终权威状态等价。
- [ ] 断线概念不移除 required member。
- [ ] 私有章节和未来材料永不进入另一人投影。
- [ ] 《雪乡》单人包继续通过。

### MP-2 · 房间、身份、邀请与选角

```text
状态    [ ] TODO
依赖    MP-1
输出    migrations + repository + lobby API/UI
```

工作：

- [ ] Supabase 无感匿名身份。
- [ ] 创建房间和短时邀请链接。
- [ ] 限制每个 principal 只有一局未完成游戏。
- [ ] 自由选角、取消选择、ready、start。
- [ ] start 原子锁定成员集合与 package version。

Gate：

- [ ] 第三人不能加入满房。
- [ ] 并发抢同一角色只有一人成功。
- [ ] 未加入者知道 session UUID 仍不能读取内容。
- [ ] 邀请满员、撤销或过期后失效。
- [ ] 清除身份后不能凭昵称或链接认领旧角色。

### MP-3 · 幂等命令与同事务 Checkpoint

```text
状态    [ ] TODO
依赖    MP-2
输出    Command Service + revision + transactional checkpoint
```

工作：

- [ ] command ID、payload hash、expected revision。
- [ ] PostgreSQL transaction advisory lock。
- [ ] 所有阶段 mutation 走统一 Command Service。
- [ ] checkpoint saver 复用同一连接。
- [ ] 并发与故障注入测试。

Gate：

- [ ] 相同 command 重试只生效一次。
- [ ] 相同 ID 不同 payload 被拒绝。
- [ ] 同 revision 并发操作至多一个按该版本成功。
- [ ] 任一故障不留下半 checkpoint、半揭晓或半推进。

### MP-4 · 聊天、结算、事件与快照

```text
状态    [ ] TODO
依赖    MP-3
输出    durable chat + secret submissions + events + snapshot
```

工作：

- [ ] 纯文字、不可编辑的有序公共聊天。
- [ ] read/close intents 与全员同步门槛。
- [ ] 秘密提交与原子统一揭晓。
- [ ] public/private room events 和 outbox。
- [ ] participant-scoped atomic snapshot。

Gate：

- [ ] 未揭晓选票不会通过 API/WS/错误泄漏。
- [ ] 聊天掉线补收顺序正确。
- [ ] worker 重启不丢事件，重复发布不重复展示。
- [ ] snapshot + replay 可重建同一玩家视图。

### MP-5 · 认证 WebSocket 与 Replay

```text
状态    [ ] TODO
依赖    MP-4
输出    ws-ticket + replay + presence + resync
```

工作：

- [ ] ticket/hello/ready/heartbeat。
- [ ] replay/live 闭合窗口。
- [ ] sequence/event 去重与 snapshot resync。
- [ ] multi-tab presence 和 disconnect grace。
- [ ] Redis routing/rate-limit/wake-up。
- [ ] 非权威远端 avatar pose。

Gate：

- [ ] 掉线期间聊天可补收。
- [ ] 掉线期间结算与推进保持暂停。
- [ ] 关闭一个 tab 不误报离线。
- [ ] 节点重启、Redis flush 不丢权威状态。
- [ ] 慢客户端被要求 resync，不拖垮服务器。

### MP-6 · 双浏览器可玩闭环

```text
状态    [ ] TODO
依赖    MP-5
输出    两个 JWT 的完整真人流程
```

```text
创建 → 邀请 → 选角 → 双方读本 → 公共讨论
→ 全员结束讨论 → 秘密投票 → 统一揭晓
→ 下一章 → 共同最终推理 → 完整复盘
```

Gate：

- [ ] 两个真实浏览器完整通过。
- [ ] 任一方在读本、讨论、提交后刷新均正确恢复。
- [ ] 私有章节和未揭晓投票不串线。
- [ ] 地图显示对方，但移动不逐帧写 Zustand/React。
- [ ] 跨天返回可继续同一局。
- [ ] 未完成结束不开放真相。

### MP-7 · 公共 AI DM 与 T-2.4 RAG

```text
状态    [ ] TODO
依赖    MP-6
输出    DmResponder + hint consent + RAG + fallback
```

工作：

- [ ] 节点式公共 `DmResponder`。
- [ ] 当前对局有界聊天摘要。
- [ ] 全知后台与 participant-safe 输出投影。
- [ ] 全员提示确认和三级升级。
- [ ] 复用 T-2.4 权限过滤和 DM-only RAG。
- [ ] prompt injection、剧透、过期输出和 provider outage 测试。

Gate：

- [ ] DM 不揭穿玩家角色陈述。
- [ ] DM 不拥有领域写工具。
- [ ] DM-only 和其他角色秘密不泄漏。
- [ ] 关闭模型后仍能通关。
- [ ] 提示只记录，不自动扣分或改结局。

### MP-8 · 稳定性、安全与发布

```text
状态    [ ] TODO
依赖    MP-7
输出    recovery/security/load report + rollback drill
```

工作：

- [ ] 双 API/WS 实例测试。
- [ ] Redis/节点/数据库断连测试。
- [ ] outbox backlog、慢消费者和长断线压测。
- [ ] command p95、replay lag、outbox age、DM fallback 指标。
- [ ] 邀请撤销、房间保留期、审计和清理任务。
- [ ] feature-flag 回滚演练。

Gate：

- [ ] 第 11 节验收矩阵全部通过。
- [ ] 再评估 4～8 人、正式账号绑定、语音和 AI NPC。

---

## 11. 验收矩阵

| 维度 | 场景 | 通过条件 |
|---|---|---|
| 阶段 | read/discuss/settle/reveal | 所有人同步且不能越相。 |
| 读本 | 私有章节、回看、后续锁定 | 只返回当前玩家授权内容。 |
| 讨论 | 全员读完、结束意向撤销 | 状态门槛准确。 |
| 投票 | 秘密提交、同时揭晓 | 揭晓前零泄漏，揭晓后票型正确。 |
| YAML | 材料节点、结算模式、分支 | 发布时严格验证。 |
| 身份 | 跨房、伪造、身份丢失 | 服务端全部拒绝。 |
| 并发 | 抢角、最后读完、最后提交 | 只发生一次状态转换。 |
| 恢复 | 每个 commit 点 crash | checkpoint/revision/event 一致。 |
| 聊天 | 掉线期间继续发言与补收 | 顺序一致且不可修改。 |
| WS | gap、multi-tab、slow client | replay 或 snapshot 恢复。 |
| Redis | flush/restart | 只损失临时 presence。 |
| DM | 停滞、提示、注入、过期 | 不剧透，失败可降级。 |
| 地图 | 双人角色、持续移动 | 无逐帧业务 store 写入。 |
| 复盘 | 正常完成与未完成 | 仅正常完成开放完整真相。 |

### 必跑命令

```bash
make test
make lint-api
make typecheck-api
npm --prefix apps/web run lint
npm --prefix apps/web run build
```

---

## 12. 迁移与回滚

### 12.1 数据迁移

- 全部 additive：先建表/列/索引，再回填，再收紧约束。
- 旧 session 默认为 `legacy_single`。
- 没有可验证 owner JWT 的历史 session 不自动认领。
- 新多人房间只使用 GameStateV2。
- 首个多人发布不删除旧单人字段。

### 12.2 Feature Flags

```text
MULTIPLAYER_V1   房间、选角和阶段流程
ROOM_EVENTS_V1   聊天、事件、outbox 和 replay
AI_DM_V1         公共 AI DM
```

### 12.3 回滚

```text
1. 关闭 AI_DM_V1，使用 YAML 固定主持文本
2. 关闭 ROOM_EVENTS_V1 live push，保留 HTTP snapshot
3. 关闭 MULTIPLAYER_V1 新房创建
4. 已有多人房间进入维护或只读
5. legacy_single 继续运行
```

---

## 13. 首版之外

```text
[ ] 4～8 人正式 UI 与压力目标
[ ] 自动匹配和公开房间
[ ] 玩家私聊
[ ] 内置语音
[ ] 图片或文件上传
[ ] 跨设备匿名身份恢复
[ ] 中途替补与房主迁移
[ ] 独立 AI NPC
[ ] 地图自由搜证
[ ] 提示扣分或影响结局
[ ] 跨局 DM 玩家记忆
```

---

## 14. 下一步

```text
[>] MP-1
    1. 编写首个双人 fixture
    2. 实现使用已冻结 GameStateV2 的纯 reducer
    3. 覆盖 read → discuss → settle → reveal 同步阶段流
    4. 用 headless tests 验证隐私、顺序无关性与单人回归

MP-0 只完成契约与发布边界；多人 runtime、数据库、WebSocket 和 UI 仍未实现。
```
