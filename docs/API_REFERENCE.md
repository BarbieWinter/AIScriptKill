# API 参考 (API Reference)

> 当前 FastAPI 源码、`script-packages/snow-village/` 单人契约和 MP-2 HTTP contract 状态。
> MP-2 persistence/snapshot/auth/schema、room repository/service/routes 与前端已集成，并已通过 focused/full
> engine、Ruff、focused BasedPyright 与 app/OpenAPI build；真实 PostgreSQL 和 live-stack Playwright 仍未
> 运行，因此多人部分不得视为 release-ready API。

## 1. 基础信息

```text
REST Base URL: /api/v1
JSON:          Content-Type: application/json
Legacy Auth:   optional Bearer <supabase_jwt>（保持现有单人兼容行为）
MP-2 Auth:     required Bearer <supabase_anonymous_jwt>
Admin Auth:    包导入/状态更新必须使用管理员 JWT
WebSocket:     /api/v1/ws/{session_id}（当前仍只有 legacy ping/pong）
```

普通 HTTP 请求体上限为 1 MiB。`POST /packages` 的 multipart 信封上限为 65 MiB，唯一 ZIP 文件最多 64 MiB；限制按 ASGI 实际接收字节累计。

业务错误使用统一信封：

```json
{
  "error": {
    "code": "ACTION_NOT_AVAILABLE",
    "message": "当前阶段未启用动作: examine_scene",
    "details": {}
  }
}
```

FastAPI/Pydantic 请求校验失败仍返回标准 HTTP 422 响应，不使用上述业务错误信封。

### 1.1 健康检查

健康检查不在 `/api/v1` 下。

#### `GET /health`

不访问数据库。

```json
{
  "status": "ok",
  "engine": "aiscriptkill",
  "version": "0.1.0"
}
```

#### `GET /health/db`

检查数据库连通性和必需表。

```json
{
  "status": "ok",
  "database": "reachable"
}
```

数据库不可达或迁移不完整时返回 503，错误码分别为 `DATABASE_UNAVAILABLE` 或 `DATABASE_SCHEMA_INCOMPLETE`。

## 2. 当前 Snow Village 内容权威

当前 `snow-village` 是 `max_players: 1` 的单人切片：

- 标题：`雪落之前：后门的脚印`
- 入口：`return_to_snow_village`
- 玩家角色：`zhuosiyuan`（卓司元）
- NPC：`wangdada`（王大达）
- 阶段：`return_to_snow_village` → `investigate_back_alley` → `confront_wangdada` → `back_door_judgement`
- 场景：`restaurant-hall`、`back-alley`
- 热点：`back-alley:back-door-traces`
- 线索：`clue-back-alley-note`（后巷便签）
- 证物：`evidence-back-door-image`（21:13 后门截图）
- 人物章节：`zhuosiyuan-chapter-01`、`zhuosiyuan-chapter-02`
- 最终判断正确选项：`C`

关键推进条件包括 `character_chapter_read`、`evidence_viewed` 和 `evidence_shown_to_npc`。仅发现证物不等于查看证物；客户端必须调用证物已查看端点。

## 3. 会话管理

### 3.0 MP-2 HTTP-only 房间 contract（IN PROGRESS）

以下 contract 已由 strict Python schemas、已挂载 FastAPI routes 和前端 client/types 对齐。已集成 anonymous
JWT dependency、feature gate、persistence metadata、immutable package snapshot、commit-free repository、
single-commit service 与前端页面，并通过 focused/full engine 和 app/OpenAPI build。真实 PostgreSQL 与
live-stack 测试尚未运行，因此不要把本节当成已发布端到端能力。

所有 MP-2 请求必须携带 Supabase anonymous access token：

```http
Authorization: Bearer <supabase_anonymous_jwt>
```

服务端验证签名、issuer、audience、expiry、UUID `sub` 和 `is_anonymous=true`，并只把验证后的 principal
UUID 传给 room service。客户端不能提交 principal/member/actor/owner。稳定身份错误为：

- 401 `AUTH_REQUIRED`：缺少 bearer；
- 401 `INVALID_TOKEN`：JWT 验证失败；
- 401 `INVALID_USER_ID`：`sub` 不是 UUID；
- 403 `ANONYMOUS_IDENTITY_REQUIRED`：首版收到非 anonymous identity；
- 503 `MULTIPLAYER_DISABLED`：`MULTIPLAYER_V1=false`。

#### Endpoint inventory

```text
POST   /sessions
GET    /sessions/current
POST   /sessions/{session_id}/invites
DELETE /sessions/{session_id}/invites/{invite_id}
POST   /session-invites/{token}/accept
GET    /sessions/{session_id}/snapshot
POST   /sessions/{session_id}/commands
```

`GET /sessions/current` 必须在动态 `/{session_id}` route 前注册。

#### `POST /sessions` — 创建 multiplayer lobby

同一路径使用 strict union 保持无 `mode` 的 legacy request 兼容。多人请求：

```json
{
  "mode": "multiplayer_v1",
  "script_id": "mp1-two-player"
}
```

响应 201：

```json
{
  "session_id": "12345678-1234-5678-1234-567812345678",
  "mode": "multiplayer_v1",
  "status": "lobby",
  "revision": 0,
  "member_id": "22345678-1234-5678-1234-567812345678",
  "created_at": "2026-07-18T12:00:00Z"
}
```

创建只允许已发布、strict two-player package。事务在同一 injected `AsyncSession` 中以 `FOR SHARE`
锁住 published package 主行，冻结完整 runtime snapshot/SHA，并与 room、host member 和 principal
reservation 最终提交一次；codec/lock 与 create service 接线已有 focused/full engine evidence。同 principal 已有
`lobby|active` reservation 时返回 409 `UNFINISHED_ROOM_EXISTS`。真实 PostgreSQL 并发/republish lane 尚未运行。

#### `GET /sessions/current` — 恢复当前房间 locator

响应是 nullable JSON。无未完成房间时为：

```json
null
```

有未完成房间时：

```json
{
  "session_id": "12345678-1234-5678-1234-567812345678",
  "mode": "multiplayer_v1",
  "status": "lobby"
}
```

只按 verified principal reservation 查询，不能用昵称、invite token、tab ID 或 session UUID 认领身份。

#### Invite lifecycle

Host 在 lobby 创建默认 15 分钟的一次性邀请：

```http
POST /sessions/12345678-1234-5678-1234-567812345678/invites
```

```json
{
  "ttl_seconds": 900
}
```

`ttl_seconds` 范围为 60–3600。响应 201：

```json
{
  "invite_id": "32345678-1234-5678-1234-567812345678",
  "token": "url-safe-token-returned-only-once",
  "expires_at": "2026-07-18T12:15:00Z"
}
```

数据库只存原 token 的 32-byte SHA-256 hash；明文 token 只在创建响应返回一次。撤销为幂等 204：

```http
DELETE /sessions/{session_id}/invites/{invite_id}
```

接受邀请不带 JSON body：

```http
POST /session-invites/{token}/accept
```

响应 200：

```json
{
  "session_id": "12345678-1234-5678-1234-567812345678",
  "status": "lobby",
  "revision": 1,
  "member_id": "42345678-1234-5678-1234-567812345678"
}
```

Token 只授权尝试加入，不授权读取房间。稳定失败包括 `INVITE_NOT_FOUND`、`INVITE_EXPIRED`、
`INVITE_REVOKED`、`INVITE_EXHAUSTED`、`ROOM_FULL`、`ROOM_NOT_IN_LOBBY` 与
`UNFINISHED_ROOM_EXISTS`。这些真实事务分支仍需 PostgreSQL gate。

#### `GET /sessions/{session_id}/snapshot` — participant-safe lobby projection

响应结构：

```json
{
  "session_id": "12345678-1234-5678-1234-567812345678",
  "mode": "multiplayer_v1",
  "status": "lobby",
  "revision": 3,
  "package": {
    "script_id": "mp1-two-player",
    "title": "两份口供",
    "version": "1.0.0"
  },
  "capacity": {"min_players": 2, "max_players": 2, "joined": 2},
  "self": {
    "member_id": "22345678-1234-5678-1234-567812345678",
    "room_role": "host",
    "character_id": "investigator",
    "ready": true
  },
  "members": [
    {
      "member_id": "22345678-1234-5678-1234-567812345678",
      "room_role": "host",
      "character_id": "investigator",
      "ready": true
    },
    {
      "member_id": "42345678-1234-5678-1234-567812345678",
      "room_role": "player",
      "character_id": "insider",
      "ready": true
    }
  ],
  "characters": [
    {
      "id": "investigator",
      "name": "调查员",
      "assigned_member_id": "22345678-1234-5678-1234-567812345678"
    },
    {
      "id": "insider",
      "name": "知情者",
      "assigned_member_id": "42345678-1234-5678-1234-567812345678"
    }
  ],
  "capabilities": {
    "can_invite": true,
    "can_assign_character": true,
    "can_ready": true,
    "can_start": true
  },
  "invites": []
}
```

只有 host 能看到无 token/hash 的 invite metadata。响应永不包含 principal IDs、完整 runtime snapshot、
章节、秘密、结局、DM guide、明文 token 或 token hash。非成员即使知道 UUID 也返回 403
`NOT_ROOM_MEMBER`。`active` 仍使用同一安全 room/start metadata，前端只显示 MP-6 placeholder。

#### `POST /sessions/{session_id}/commands` — MP-2 lobby commands

MP-2 只接受四种 command type：

```json
{
  "command_id": "52345678-1234-5678-1234-567812345678",
  "expected_revision": 3,
  "type": "room.assign_character",
  "payload": {"character_id": "investigator"}
}
```

```json
{
  "command_id": "62345678-1234-5678-1234-567812345678",
  "expected_revision": 4,
  "type": "room.unassign_character",
  "payload": {}
}
```

```json
{
  "command_id": "72345678-1234-5678-1234-567812345678",
  "expected_revision": 5,
  "type": "room.ready",
  "payload": {"ready": true}
}
```

```json
{
  "command_id": "82345678-1234-5678-1234-567812345678",
  "expected_revision": 7,
  "type": "room.start",
  "payload": {}
}
```

成功响应使用冻结的 `CommandResultV1`：

```json
{
  "command_id": "82345678-1234-5678-1234-567812345678",
  "status": "accepted",
  "revision": 8,
  "event_sequence": 0,
  "result": {"event_ids": []},
  "error": null,
  "replayed": false
}
```

MP-2 不持久化 command id/payload hash，也不提供 replay；`command_id` 是 envelope 字段，不能被当作
已实现的幂等保证。响应丢失或 `REVISION_MISMATCH` 时客户端刷新 snapshot，不自动重放 mutation。
阶段、hint、resync 和 `room.end_incomplete` 命令在 MP-2 返回 422 `COMMAND_NOT_AVAILABLE`。

选角和 ready 只作用于本人；assign/unassign 清除本人 ready，`ready=true` 要求已经选角。start 仅 host，
并要求房间已满、角色完整且互异、全员 ready、snapshot digest 有效；成功时按
`(joined_at, member_id)` 固定 required members，初始化 MP-1 `GameStateV2`，更新为 `active` 并撤销剩余
邀请。上述原子 start 必须由真实 PostgreSQL tests 验证，mocked browser test 不能证明其事务性。

### 3.1 `POST /sessions` — 创建 legacy 单人会话

只会从已发布剧本包开局；偏好角色必须是该包的可玩角色。

请求：

```json
{
  "script_id": "snow-village",
  "player_name": "卓司元",
  "preferred_character_id": "zhuosiyuan"
}
```

响应 200：

```json
{
  "session_id": "12345678-1234-5678-1234-567812345678",
  "script_id": "snow-village",
  "status": "in_progress",
  "current_stage": "return_to_snow_village",
  "player_character_id": "zhuosiyuan",
  "available_actions": [
    "talk_to_npc",
    "request_advance",
    "open_clue_board"
  ],
  "created_at": "2026-07-17T12:00:00Z"
}
```

`script_id`、`player_name`、`preferred_character_id` 都是必填非空字符串。没有匹配的已发布包或可玩角色时返回 `SCRIPT_PACKAGE_NOT_FOUND`。

### 3.2 `GET /sessions/{session_id}` — 会话状态

入口阶段示例：

```json
{
  "session_id": "12345678-1234-5678-1234-567812345678",
  "script_id": "snow-village",
  "status": "in_progress",
  "current_stage": "return_to_snow_village",
  "stage_name": "炉火未熄",
  "player_character_id": "zhuosiyuan",
  "available_actions": [
    "talk_to_npc",
    "request_advance",
    "open_clue_board"
  ],
  "available_characters": ["wangdada"],
  "unlocked_clues_count": 0,
  "total_clues_in_round": 0,
  "discovered_evidences": [],
  "viewed_evidences": [],
  "current_scene": "restaurant-hall",
  "pending_media": []
}
```

`total_clues_in_round` 当前映射器返回已解锁线索数量，不是包内该轮总量。

### 3.3 `GET /sessions/{session_id}/presentation` — 安全展示投影

返回当前阶段、场景、公开热点和可选判断题；不会返回热点执行动作或正确答案。私有 Storage 定位符不会直接变成浏览器 URL，因此当前导入资源的 `background_url` 可为 `null`。

调查后巷示例：

```json
{
  "stage": {
    "id": "investigate_back_alley",
    "name": "调查后巷",
    "available_actions": [
      "examine_scene",
      "talk_to_npc",
      "request_advance",
      "open_clue_board"
    ],
    "available_characters": ["wangdada"]
  },
  "scene": {
    "id": "back-alley",
    "name": "饭馆后巷",
    "description": "风雪覆盖的狭窄后巷，后门旁的积雪有新鲜扰动。",
    "ambient_color": "#17243a",
    "background_url": null,
    "hotspots": [
      {
        "id": "back-door-traces",
        "label": "后门旁的痕迹",
        "x": 58.0,
        "y": 44.0,
        "width": null,
        "height": null
      }
    ]
  },
  "judgement": null
}
```

最终阶段的 `judgement` 为：

```json
{
  "title": null,
  "question": "根据当前材料，哪项最符合已证实事实？",
  "options": [
    {"id": "A", "text": "陈吉在21:13从后门进入，目的是偷走旧账本。"},
    {"id": "B", "text": "王大达伪造便签，试图掩盖自己与旧案的关系。"},
    {"id": "C", "text": "王大达关于没人来过的说法不完整；至少可确认后门在21:13半开，但不能确认开门者和目的。"},
    {"id": "D", "text": "后门异常证明饭馆当晚发生过犯罪。"}
  ]
}
```

### 3.4 `PATCH /sessions/{session_id}` — 旧恢复入口（禁用）

请求模型仍只接受：

```json
{
  "action": "restore",
  "checkpoint_id": "ckpt-456"
}
```

合法 UUID 当前稳定返回 HTTP 409；不会访问数据库或执行检查点恢复：

```json
{
  "error": {
    "code": "SESSION_RESTORE_UNAVAILABLE",
    "message": "会话检查点恢复当前不可用",
    "details": {}
  }
}
```

非法 UUID 先返回 `INVALID_SESSION_ID`（400）。`CHECKPOINT_NOT_FOUND` 已从这条公开恢复路径移除，当前不可达；请求体不合法仍为 422。

## 4. 游戏操作

### 4.1 `POST /sessions/{session_id}/actions`

生产路径是 `LangGraphRuntimeActionExecutor`：服务端从已发布包重建 `ScriptEngine`，恢复 LangGraph 状态，校验动作和目标，执行图，再持久化会话投影。它不是固定示例响应器。

请求模型字段如下；未知字段会被拒绝。`action` 的允许值是 `talk_to_npc`、`examine_scene`、`show_evidence`、`use_card`、`open_clue_board`、`request_advance`，但动作还必须出现在当前阶段的 `available_actions` 中。

```json
{
  "action": "examine_scene",
  "character_id": null,
  "message": null,
  "scene_id": "back-alley",
  "hotspot_id": "back-door-traces",
  "evidence_id": null,
  "card_id": null,
  "target_character_id": null,
  "reason": null
}
```

调用方通常只发送动作所需字段，不需要显式发送其余 `null` 字段。

#### MP-3 durable legacy action

`legacy_single` 客户端可以为同一请求附带成对字段 `command_id` 与 `expected_revision`。两者必须同时存在；`command_id` 是一次用户意图的 UUID，`expected_revision` 是提交前最后看到的会话 revision。

```json
{
  "action": "talk_to_npc",
  "character_id": "wangdada",
  "message": "今晚还有谁来过？",
  "command_id": "b0e5f7b8-b607-4d69-aab1-4cbe10b7b53d",
  "expected_revision": 3
}
```

成功响应封装原动作结果，并返回权威坐标：

```json
{
  "command_id": "b0e5f7b8-b607-4d69-aab1-4cbe10b7b53d",
  "status": "succeeded",
  "revision": 4,
  "event_sequence_from": 4,
  "event_sequence_to": 4,
  "result": {
    "type": "npc_response",
    "character_id": "wangdada",
    "text": "我没有看清。",
    "emotion": "normal",
    "state_changes": {},
    "triggered_events": [],
    "media_triggers": []
  },
  "error_code": null,
  "error_details": {}
}
```

恢复端点：

- `GET /sessions/{session_id}/commands/{command_id}` 返回 `processing | succeeded | rejected | failed` receipt。
- `GET /sessions/{session_id}/events?after_sequence={cursor}&limit={1..500}` 返回按 sequence 排序的公开事件页及权威 legacy snapshot。

客户端必须在第一次 POST 前生成 UUID，并在响应不确定时保留完整不可变 envelope。先查询同一 UUID 的 receipt；只有 `COMMAND_NOT_FOUND` 才允许至多一次原样重发。`processing` 应有界轮询，耗尽后进入人工可恢复的 uncertain 状态。`SESSION_REVISION_CONFLICT`、`COMMAND_ID_REUSE`、terminal `rejected`/`failed` 不得自动重放；冲突后先同步权威 snapshot/events，由新的用户手势产生新 UUID。

事件 cursor 校验要求忽略 `sequence <= cursor` 的重复事件，并只接受严格的 `cursor + 1`。gap、无效 future cursor 或 `reset_required` 只能触发一次 cursor-0 reset；事件 payload 不用于浏览器侧重放 gameplay 副作用。

此 durable 协议只覆盖本端点的 `legacy_single` 分支。`POST /sessions/{session_id}/commands` 仍是 MP-2 lobby command，不应描述为 durable multiplayer gameplay；WebSocket 也不承担本恢复协议。

#### 对话

```json
{
  "action": "talk_to_npc",
  "character_id": "wangdada",
  "message": "今晚还有谁来过？"
}
```

响应结构：

```json
{
  "type": "npc_response",
  "character_id": "wangdada",
  "text": "我只会根据当前阶段和剧本包中获准的事实回答。",
  "emotion": "normal",
  "state_changes": {},
  "triggered_events": [],
  "media_triggers": []
}
```

`text` 和 `emotion` 由当前 NPC responder 生成，示例文字不是稳定常量；其余字段与 schema 一致。

#### 调查热点

请求：

```json
{
  "action": "examine_scene",
  "scene_id": "back-alley",
  "hotspot_id": "back-door-traces"
}
```

当前包首次调查响应：

```json
{
  "type": "scene_result",
  "scene_id": "back-alley",
  "hotspot_id": "back-door-traces",
  "dm_narration": "你拨开门槛旁的薄雪，找到一张折起的便签，也保存了邻近摄像头在21:13拍到的后门截图。",
  "discovered_clues": [
    {"clue_id": "clue-back-alley-note", "name": "后巷便签"}
  ],
  "discovered_evidences": ["evidence-back-door-image"],
  "media_triggers": []
}
```

#### 出示证物

```json
{
  "action": "show_evidence",
  "character_id": "wangdada",
  "evidence_id": "evidence-back-door-image"
}
```

响应结构：

```json
{
  "type": "evidence_reaction",
  "character_id": "wangdada",
  "text": "后门当时确实开着，但我没看见是谁开的。",
  "emotion": "normal",
  "state_changes": {},
  "triggered_dialog": "",
  "media_triggers": []
}
```

证物必须已经发现，角色必须在当前阶段可用；NPC 文本仍经过生产 responder。

#### 请求推进

条件未满足时仍返回 200 和 `advance_denied`：

```json
{
  "type": "advance_denied",
  "reason": "当前阶段的推进条件尚未满足。",
  "hint": "还需完成：阅读人物章节「炉火未熄」、与王大达交谈。",
  "suggested_action": "talk_to_npc",
  "suggested_target": "wangdada",
  "requirements": [
    {"label": "阅读人物章节「炉火未熄」", "met": false},
    {"label": "与王大达交谈", "met": false},
    {"label": "点击推进", "met": true}
  ]
}
```

满足入口阶段条件后：

```json
{
  "type": "stage_transition",
  "from_stage": "return_to_snow_village",
  "to_stage": "investigate_back_alley",
  "transition_events": [
    {
      "action": "dm_narrate",
      "asset_id": null,
      "text": "后巷的雪面被扰动过。调查后门旁的痕迹，查看发现的图片后再推进。"
    }
  ],
  "new_state": {
    "current_stage": "investigate_back_alley",
    "available_actions": [
      "examine_scene",
      "talk_to_npc",
      "request_advance",
      "open_clue_board"
    ]
  }
}
```

`open_clue_board` 由前端本地打开，后端返回 `advance_denied`，并提示调用 clues 端点。当前 Snow Village 不启用 `use_card`。

### 4.2 `POST /sessions/{session_id}/final-submission`

仅在带有效 `special_rules.judgement` 的当前阶段可提交。请求只有一个字段：

```json
{
  "option": "C"
}
```

正确提交响应 200：

```json
{
  "type": "submission_result",
  "correct": true,
  "score": 100,
  "detail": {
    "selected_option": "C",
    "correct_option": "C",
    "evidence_boundary": "该选项与当前阶段声明的正确判断一致。",
    "npc_disclosure": null
  },
  "ending_id": "judgement_correct",
  "triggered_events": [
    {
      "action": "dm_narrate",
      "asset_id": null,
      "text": "你的判断符合当前阶段的答案。"
    }
  ]
}
```

错误但已声明的选项得到 `correct: false`、`score: 0`、`ending_id: judgement_incorrect`。当前阶段没有判断时返回 `JUDGMENT_UNAVAILABLE`；选项不在 A–D 中返回 `INVALID_JUDGMENT_OPTION`。

## 5. 会话内容查询

### 5.1 `GET /sessions/{session_id}/clues`

```json
{
  "clues": [
    {
      "id": "clue-back-alley-note",
      "name": "后巷便签",
      "image_url": "",
      "description": "老王：腊肉不用留。旧账本要是还在后屋，明早前拿走。别让孩子们看见。",
      "is_key": true,
      "importance": 4,
      "discovered_at": "2026-07-17T12:10:00Z",
      "status": "unlocked"
    }
  ]
}
```

### 5.2 `GET /sessions/{session_id}/evidences`

```json
{
  "evidences": [
    {
      "id": "evidence-back-door-image",
      "name": "21:13 后门截图",
      "image_url": "storage://script-assets/snow-village/assets/evidences/back-door-2113.svg",
      "description": "21:13 的固定摄像头画面：王氏杀猪菜后门半开，门内透出暖黄色灯光，画面边缘有无法辨认身份的深色影子。",
      "status": "unlocked",
      "can_show_to_npc": true,
      "shown_to_characters": []
    }
  ]
}
```

Storage bucket 可配置，因此 `image_url` 中的 bucket 名不保证恒为 `script-assets`；当前 API 返回私有定位符，不签发浏览器 URL。

### 5.3 `POST /sessions/{session_id}/evidences/{evidence_id}/viewed`

请求无 JSON body。只允许把当前会话已发现证物单调升级为已查看。

```json
{
  "evidence_id": "evidence-back-door-image",
  "status": "viewed"
}
```

未发现证物返回 `EVIDENCE_NOT_DISCOVERED`（404）。升级后 `GET /sessions/{session_id}` 的 `viewed_evidences` 包含该 ID。

### 5.4 `GET /sessions/{session_id}/character-chapters`

只列当前玩家角色已解锁章节，不返回正文。开局示例：

```json
{
  "chapters": [
    {
      "id": "zhuosiyuan-chapter-01",
      "character_id": "zhuosiyuan",
      "order": 1,
      "title": "炉火未熄",
      "status": "unlocked"
    }
  ]
}
```

第二章 `zhuosiyuan-chapter-02` 在进入 `confront_wangdada` 时解锁。

### 5.5 `GET /sessions/{session_id}/character-chapters/{chapter_id}`

读取已授权 Markdown 正文，并把状态持久化为 `viewed`：

```json
{
  "id": "zhuosiyuan-chapter-01",
  "character_id": "zhuosiyuan",
  "order": 1,
  "title": "炉火未熄",
  "status": "viewed",
  "content": "雪把“王氏杀猪菜”的招牌压得微微倾斜。\n\n……"
}
```

未解锁、其他角色或不存在的章节统一返回 `CHARACTER_CHAPTER_NOT_FOUND`（404）。

### 5.6 其他查询

#### `GET /sessions/{session_id}/characters`

```json
{
  "characters": [
    {
      "id": "wangdada",
      "name": "王大达",
      "portrait_url": "",
      "current_mood": "normal",
      "mood_description": "状态正常",
      "dialogue_available": true
    },
    {
      "id": "zhuosiyuan",
      "name": "卓司元",
      "portrait_url": "",
      "current_mood": "normal",
      "mood_description": "状态正常",
      "dialogue_available": true
    }
  ]
}
```

#### `GET /sessions/{session_id}/chat-history`

```json
{
  "messages": [
    {
      "id": "12345678-1234-5678-1234-567812345678:0",
      "role": "player",
      "character_id": null,
      "text": "今晚还有谁来过？",
      "timestamp": "2026-07-17T12:05:00Z",
      "emotion": null
    }
  ],
  "next_page_token": null
}
```

#### `GET /sessions/{session_id}/cards`

当前 Snow Village 没有 `prop` 或 `skill_card` 证物：

```json
{
  "cards": []
}
```

## 6. 剧本包 API

### 6.1 `GET /packages`

只返回已发布包。

```json
{
  "packages": [
    {
      "id": "snow-village",
      "title": "雪落之前：后门的脚印",
      "description": "卓司元调查王氏杀猪菜后门异常的首个单人垂直切片。",
      "poster_url": "",
      "difficulty": 1,
      "duration_minutes": 30,
      "genre": ["悬疑", "互动小说"],
      "status": "published",
      "player_count": 1
    }
  ]
}
```

### 6.2 `GET /packages/{package_id}`

返回与列表元素相同的 `PackageSummary`，不是包含阶段或角色的完整包：

```json
{
  "id": "snow-village",
  "title": "雪落之前：后门的脚印",
  "description": "卓司元调查王氏杀猪菜后门异常的首个单人垂直切片。",
  "poster_url": "",
  "difficulty": 1,
  "duration_minutes": 30,
  "genre": ["悬疑", "互动小说"],
  "status": "published",
  "player_count": 1
}
```

不存在或未发布时返回 `PACKAGE_NOT_FOUND`（404）。

### 6.3 `POST /packages` — 管理员导入

`publish` 是 URL query 参数，不是 multipart 字段。multipart 必须且只能包含一个名为 `file` 的文件部件：

```bash
curl -X POST \
  -H "Authorization: Bearer ${ADMIN_JWT}" \
  -F "file=@snow-village.zip;type=application/zip" \
  "http://localhost:8000/api/v1/packages?publish=true"
```

响应 200：

```json
{
  "package_id": "snow-village",
  "title": "雪落之前：后门的脚印",
  "status": "published",
  "validation": {
    "valid": true,
    "warnings": [],
    "errors": []
  }
}
```

省略 `publish=true` 时默认导入为 `draft`。鉴权在 multipart 解析和 ZIP 读取前完成。

### 6.4 `PATCH /packages/{package_id}` — 管理员状态更新

```json
{
  "status": "published"
}
```

允许状态：`draft`、`importing`、`published`、`archived`。

```json
{
  "package_id": "snow-village",
  "status": "published",
  "published_at": "2026-07-17T14:00:00Z"
}
```

## 7. 评分与复盘

### `GET /sessions/{session_id}/review`

正确提交 `{"option":"C"}` 后，当前评分映射为 100 分、评级 A：

```json
{
  "session_id": "12345678-1234-5678-1234-567812345678",
  "script_id": "snow-village",
  "score": 100,
  "max_score": 100,
  "rating": "A",
  "duration_minutes": 0,
  "breakdown": {
    "suspect_correct": true,
    "motive_correct": true,
    "key_evidence_hit_rate": "1/1",
    "wrong_accusations": 0,
    "total_clues_found": 1,
    "total_clues_available": 1,
    "clue_coverage": "100%",
    "hints_used": 0
  },
  "missed_key_clues": [],
  "optimal_path": [
    "clue-back-alley-note",
    "evidence-back-door-image"
  ],
  "player_path": [
    "clue-back-alley-note",
    "evidence-back-door-image"
  ],
  "truth_summary": "已证实的范围仅限21:13后门半开、门内灯光和不可辨认的影子。王大达承认后来发现门闩未扣严并重新扣好，但仍不能据此确认开门者、进出方向、目的或犯罪。"
}
```

错误选项为 0 分、评级“未通过”、`key_evidence_hit_rate: "0/1"`、`wrong_accusations: 1`。尚无持久化复盘时返回合成的 0 分、评级 `N/A` 和 `truth_summary: "尚未完成最终推理。"`。

## 8. WebSocket

### 8.1 当前已实现：仅心跳

连接地址：

```text
ws://host/api/v1/ws/{session_id}
```

`session_id` 必须是 UUID。当前端点不验证 JWT，也不绑定数据库会话；它只处理 JSON 文本 `session.ping`：

```json
{
  "type": "session.ping",
  "data": {}
}
```

响应：

```json
{
  "type": "session.pong",
  "data": {
    "session_id": "12345678-1234-5678-1234-567812345678"
  }
}
```

当前资源边界：单条消息 64 KiB、全局 100 个连接、单客户端 4 个连接、每连接每分钟 30 条消息、60 秒空闲超时；binary、非法 JSON、超限消息会关闭连接。除 `session.ping` 外的 JSON 文本当前不会得到玩法响应。

### 8.2 未实现的多人/事件传输

旧文档中的 `chat.message`、`chat.send`、`action.perform`、`stage.changed`、`clue.unlocked`、`evidence.discovered`、`media.*`、`npc.state_changed`、`event.triggered` 和 `hint.shown` 示例都不是当前 wire contract。它们属于未来多人房间/事件流设计；当前服务端既不会发送，也不会处理。MP-0 仅有独立 authoring contract，不包含 WebSocket 命令或事件实现。

## 9. 错误码

### 9.1 当前 legacy 公开错误码

| HTTP | 错误码 | 说明 |
|---:|---|---|
| 400 | `INVALID_SESSION_ID` | session id 不是 UUID |
| 400 | `INVALID_USER_ID` | JWT 用户 id 不是 UUID |
| 400 | `ACTION_NOT_AVAILABLE` | 当前阶段未启用动作 |
| 400 | `ACTION_TARGET_REQUIRED` | 动作缺少目标 |
| 400 | `ACTION_TARGET_INVALID` | 动作目标格式错误 |
| 400 | `ACTION_TARGET_UNAVAILABLE` | 场景、热点或角色当前不可用 |
| 400 | `EVIDENCE_NOT_DISCOVERED` | 动作尝试使用未发现证物 |
| 400 | `JUDGMENT_UNAVAILABLE` | 当前阶段没有有效判断题 |
| 400 | `INVALID_JUDGMENT_OPTION` | 最终选项不在阶段声明中 |
| 400 | `EMPTY_PACKAGE_UPLOAD` | 上传文件为空 |
| 400 | `PACKAGE_UPLOAD_INVALID` | multipart 或唯一 `file` 部件不合法 |
| 400 | `PACKAGE_UPLOAD_TOO_LARGE` | ZIP 超过 64 MiB |
| 400 | `PACKAGE_*` / `INVALID_PACKAGE_*` | ZIP、YAML、schema、引用或资源校验失败 |
| 401 | `INVALID_TOKEN` | Bearer JWT 无效 |
| 401 | `AUTH_REQUIRED` | 管理端点没有登录凭据 |
| 403 | `ADMIN_REQUIRED` | JWT 没有管理员/owner 角色 |
| 404 | `SESSION_NOT_FOUND` | 会话不存在或调用者无权访问 |
| 404 | `SCRIPT_PACKAGE_NOT_FOUND` | 没有已发布运行时包可用于开局/动作 |
| 404 | `SESSION_PRESENTATION_NOT_FOUND` | 当前阶段或场景展示记录不可用 |
| 404 | `EVIDENCE_NOT_DISCOVERED` | 查看端点找不到已发现证物 |
| 404 | `CHARACTER_CHAPTER_NOT_FOUND` | 章节不存在、未解锁或不属于玩家角色 |
| 404 | `PACKAGE_NOT_FOUND` | 包不存在或未发布 |
| 409 | `SESSION_RESTORE_UNAVAILABLE` | 旧检查点恢复端点当前禁用 |
| 413 | `REQUEST_BODY_TOO_LARGE` | ASGI 累计请求体超过路由预算 |
| 422 | FastAPI validation error | 请求字段缺失、值非法或包含未知字段 |
| 429 | `RATE_LIMITED` | HTTP 请求过于频繁 |
| 503 | `DATABASE_SCHEMA_INCOMPLETE` | 必需迁移表缺失 |
| 503 | `DATABASE_UNAVAILABLE` | 数据库连接或 SQL 执行不可用 |

`CHECKPOINT_NOT_FOUND` 不是当前公开可达错误；恢复入口在任何数据库检查前返回 409。

### 9.2 MP-2 contract 错误码（已接线；真实数据库 gate 未运行）

| HTTP | 错误码 | 说明 |
|---:|---|---|
| 401 | `AUTH_REQUIRED` | 多人请求缺少 bearer token |
| 401 | `INVALID_TOKEN` | Supabase JWT 验证失败 |
| 401 | `INVALID_USER_ID` | JWT `sub` 不是 UUID |
| 403 | `ANONYMOUS_IDENTITY_REQUIRED` | 首版拒绝非 anonymous identity |
| 403 | `NOT_ROOM_MEMBER` | verified principal 不是该 room member |
| 403 | `HOST_REQUIRED` | 非 host 执行 invite/start |
| 404 | `INVITE_NOT_FOUND` | token 不存在或不公开存在性 |
| 409 | `UNFINISHED_ROOM_EXISTS` | principal 已有 lobby/active reservation |
| 410 | `INVITE_EXPIRED` / `INVITE_REVOKED` | 邀请已过期或撤销 |
| 409 | `INVITE_EXHAUSTED` | 邀请使用次数已耗尽 |
| 409 | `ROOM_FULL` | joined members 已达 frozen capacity |
| 409 | `ROOM_NOT_IN_LOBBY` | room 已 active/terminal |
| 409 | `REVISION_MISMATCH` | expected revision 过期，先刷新 snapshot |
| 409 | `CHARACTER_ALREADY_ASSIGNED` | 同房角色唯一约束冲突 |
| 409 | `CHARACTER_REQUIRED` | ready 时尚未选角 |
| 422 | `CHARACTER_NOT_PLAYABLE` | 请求的角色不在 frozen playable set |
| 409 | `ROOM_NOT_FULL` / `ASSIGNMENTS_INCOMPLETE` / `PLAYERS_NOT_READY` | start precondition 失败 |
| 409 | `ROOM_PACKAGE_INVALID` | frozen snapshot digest/structure/stage 无效，fail closed |
| 422 | `PACKAGE_NOT_MULTIPLAYER` | create 目标包不满足 strict MP-2 policy |
| 422 | `COMMAND_NOT_AVAILABLE` | MP-2 收到 lobby 范围外 command |
| 503 | `MULTIPLAYER_DISABLED` | feature flag 关闭 |

状态码和 details 必须以最终 route/service 实现与测试为准。前端已提供稳定 code-to-message 映射，
但这不证明后端所有分支已经 live 验证。
