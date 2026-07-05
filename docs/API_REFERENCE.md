# API 参考 (API Reference)

> 前后端通信契约。包括 REST API 和 WebSocket 协议。

---

## 1. 基础信息

```
Base URL:    /api/v1
Content-Type: application/json
Auth:        Bearer <supabase_jwt> 或匿名token
WebSocket:   /api/v1/ws/{session_id}
```

错误响应格式：
```json
{
  "error": {
    "code": "STAGE_NOT_ACCESSIBLE",
    "message": "当前阶段不允许此操作",
    "details": {}
  }
}
```

---

## 2. REST API

### 2.1 会话管理

#### `POST /sessions` — 创建游戏会话
```json
// Request
{
  "script_id": "snow-village",
  "player_name": "玩家小明",
  "preferred_character_id": "zhuosiyuan"
}
// Response 200
{
  "session_id": "abc-123",
  "script_id": "snow-village",
  "status": "in_progress",
  "current_stage": "prologue",
  "player_character_id": "zhuosiyuan",
  "available_actions": ["talk_to_npc", "examine_scene", "open_clue_board"],
  "created_at": "2026-07-05T12:00:00Z"
}
```

#### `GET /sessions/{session_id}` — 获取会话状态
```json
// Response 200
{
  "session_id": "abc-123",
  "script_id": "snow-village",
  "status": "in_progress",
  "current_stage": "act1_investigation",
  "stage_name": "第一幕·第一轮搜证",
  "player_character_id": "zhuosiyuan",
  "available_actions": ["talk_to_npc", "examine_scene", "show_evidence", "use_card", "open_clue_board", "request_advance"],
  "available_characters": ["zhuosiyuan", "cuikaiqiang", "wangdada"],
  "unlocked_clues_count": 2,
  "total_clues_in_round": 5,
  "discovered_evidences": ["broken_glass"],
  "current_scene": "crime_scene",
  "pending_media": [
    {"id": "bgm_investigation", "type": "bgm", "status": "playing"}
  ]
}
```

#### `PATCH /sessions/{session_id}` — 更新会话（恢复/存档操作）
```json
// Request
{
  "action": "restore",
  "checkpoint_id": "ckpt-456"
}
// Response 200
{
  "session_id": "abc-123",
  "status": "restored",
  "current_stage": "act1_investigation",
  "restored_from": "ckpt-456"
}
```

---

### 2.2 游戏操作

#### `POST /sessions/{session_id}/actions` — 执行游戏操作
```json
// 操作类型1：对话角色
{
  "action": "talk_to_npc",
  "character_id": "wangdada",
  "message": "你昨晚在哪？"
}
// Response 200
{
  "type": "npc_response",
  "character_id": "wangdada",
  "text": "我昨晚？我一直在厨房忙活啊，没出过门。",
  "emotion": "normal",
  "state_changes": {"trust": -5, "nervous": 10},
  "triggered_events": [],
  "media_triggers": []
}

// 操作类型2：调查场景热点
{
  "action": "examine_scene",
  "scene_id": "crime_scene",
  "hotspot_id": "back_door"
}
// Response 200
{
  "type": "scene_result",
  "scene_id": "crime_scene",
  "hotspot_id": "back_door",
  "dm_narration": "你推开后门，雪地上有杂乱的脚印……",
  "discovered_clues": [{"clue_id": "broken_glass", "name": "碎玻璃碴"}],
  "discovered_evidences": [],
  "media_triggers": [{"action": "play_audio", "asset_id": "sfx_discovery"}]
}

// 操作类型3：出示证物
{
  "action": "show_evidence",
  "character_id": "wangdada",
  "evidence_id": "bloody_knife"
}
// Response 200
{
  "type": "evidence_reaction",
  "character_id": "wangdada",
  "text": "这刀是我家的！但昨晚它明明在厨房里……",
  "emotion": "shocked",
  "state_changes": {"shock": 20, "fear": 30, "trust": -15},
  "triggered_dialog": "knife_reaction",
  "media_triggers": [{"action": "play_audio", "asset_id": "sfx_tension"}]
}

// 操作类型4：使用卡牌
{
  "action": "use_card",
  "card_id": "interrogation_card",
  "target_character_id": "wangdada"
}
// Response 200
{
  "type": "card_result",
  "card_id": "interrogation_card",
  "remaining_uses": 1,
  "effect": "skill_interrogation",
  "character_id": "wangdada",
  "text": "（被你严厉质问，王大达明显动摇了）",
  "effect_description": "王大达的紧张+30，可疑度+20"
}

// 操作类型5：请求推进阶段
{
  "action": "request_advance",
  "reason": "我感觉已经调查得差不多了"
}
// Response 200 (如果条件满足)
{
  "type": "stage_transition",
  "from_stage": "act1_investigation",
  "to_stage": "act1_event",
  "transition_events": [
    {"action": "play_audio", "asset_id": "broadcast_1"},
    {"action": "dm_narrate", "text": "突然，村口的广播响了起来……"}
  ],
  "new_state": {
    "current_stage": "act1_event",
    "available_actions": ["talk_to_npc", "examine_scene", "show_evidence"]
  }
}
// Response 200 (如果条件不满足)
{
  "type": "advance_denied",
  "reason": "你还没有找到足够的线索。继续调查吧。",
  "hint": "试试和王大达聊聊昨晚的事",
  "suggested_action": "talk_to_npc",
  "suggested_target": "wangdada"
}
```

#### `POST /sessions/{session_id}/final-submission` — 最终推理提交
```json
// Request
{
  "suspect": "chengjun",
  "motive": "复仇",
  "key_evidences": ["bloody_knife", "threatening_letter", "alibi_hole"],
  "deduction": "程俊假扮成王大达潜伏在雪乡，因为多年前的冤案杀害了李白。"
}
// Response 200
{
  "type": "submission_result",
  "correct": true,
  "score": 85,
  "detail": {
    "correct_suspect": true,
    "correct_motive": true,
    "key_evidence_hit_rate": "3/5",
    "missed_key_evidences": ["hidden_letter", "phone_record"]
  },
  "ending_id": "truth_revealed",
  "triggered_events": [
    {"action": "play_audio", "asset_id": "ending_bgm_true"},
    {"action": "dm_narrate", "text": "真相，终于浮出水面……"}
  ]
}
```

---

### 2.3 数据查询

#### `GET /sessions/{session_id}/clues` — 获取已解锁线索
```json
// Response 200
{
  "clues": [
    {
      "id": "bloody_footprint",
      "name": "带血脚印",
      "image_url": "/storage/clues/1.jpg",
      "description": "雪地上有一串带血的脚印……",
      "is_key": true,
      "importance": 4,
      "discovered_at": "2026-07-05T12:10:00Z",
      "status": "discovered"
    }
  ]
}
```

#### `GET /sessions/{session_id}/evidences` — 获取已发现证物
```json
// Response 200
{
  "evidences": [
    {
      "id": "broken_glass",
      "name": "碎玻璃碴",
      "image_url": "/storage/evidences/glass.jpg",
      "description": "饭店后门地上有破碎的玻璃杯",
      "status": "discovered",
      "can_show_to_npc": true,
      "shown_to_characters": ["wangdada"]
    }
  ]
}
```

#### `GET /sessions/{session_id}/characters` — 获取当前场景角色
```json
// Response 200
{
  "characters": [
    {
      "id": "wangdada",
      "name": "王大达",
      "portrait_url": "/storage/portraits/wangdada.jpg",
      "current_mood": "nervous",
      "mood_description": "表面上还在笑，但说话有些结巴",
      "dialogue_available": true
    }
  ]
}
```

#### `GET /sessions/{session_id}/chat-history` — 获取聊天记录
```json
// Response 200
{
  "messages": [
    {
      "id": "msg-1",
      "role": "player",
      "character_id": null,
      "text": "你昨晚在哪？",
      "timestamp": "2026-07-05T12:15:00Z"
    },
    {
      "id": "msg-2",
      "role": "npc",
      "character_id": "wangdada",
      "text": "我昨晚一直在厨房忙活。",
      "emotion": "normal",
      "timestamp": "2026-07-05T12:15:02Z"
    }
  ],
  "next_page_token": "msg-50"
}
```

#### `GET /sessions/{session_id}/cards` — 获取可用卡牌
```json
// Response 200
{
  "cards": [
    {
      "id": "interrogation_card",
      "name": "质问卡",
      "type": "skill",
      "image_url": "/storage/cards/skill_1.jpg",
      "description": "严厉质问一个角色，使其紧张度大幅上升",
      "max_uses": 3,
      "remaining_uses": 2,
      "available": true
    }
  ]
}
```

---

### 2.4 剧本包管理（后台）

#### `POST /packages` — 导入剧本包
```json
// Request (multipart/form-data)
{
  "file": "<zip archive of script-package>",
  "publish": false
}
// Response 200
{
  "package_id": "snow-village",
  "title": "雪乡连环杀人事件",
  "status": "imported",
  "validation": {
    "valid": true,
    "warnings": ["角色'程俊'没有出现在任何stage的可用角色列表中"],
    "errors": []
  }
}
```

#### `PATCH /packages/{package_id}` — 更新剧本包
```json
// Request
{
  "status": "published"
}
// Response 200
{
  "package_id": "snow-village",
  "status": "published",
  "published_at": "2026-07-05T14:00:00Z"
}
```

#### `GET /packages` — 剧本包列表（前台选本）
```json
// Response 200
{
  "packages": [
    {
      "id": "snow-village",
      "title": "雪乡连环杀人事件",
      "description": "雪乡，一个被大雪覆盖的东北村庄……",
      "poster_url": "/storage/posters/main.jpg",
      "difficulty": 3,
      "duration_minutes": 120,
      "genre": ["悬疑", "推理", "惊悚"],
      "status": "published",
      "player_count": 1
    }
  ]
}
```

---

### 2.5 评分与复盘

#### `GET /sessions/{session_id}/review` — 获取复盘数据
```json
// Response 200
{
  "session_id": "abc-123",
  "script_id": "snow-village",
  "score": 85,
  "max_score": 100,
  "rating": "S",
  "duration_minutes": 68,
  "breakdown": {
    "suspect_correct": true,
    "motive_correct": true,
    "key_evidence_hit_rate": "3/5",
    "wrong_accusations": 1,
    "total_clues_found": 12,
    "total_clues_available": 18,
    "clue_coverage": "67%",
    "hints_used": 0
  },
  "missed_key_clues": [
    {"id": "hidden_letter", "name": "隐藏的信", "description": "藏在床板下的信"}
  ],
  "optimal_path": ["bloody_footprint", "bloody_knife", "threatening_letter", "alibi_hole"],
  "player_path": ["bloody_footprint", "broken_glass", "bloody_knife"],
  "truth_summary": "程俊为了多年前的冤案，化名王大达潜伏在雪乡……"
}
```

---

## 3. WebSocket 协议

### 3.1 连接

```
ws://host/api/v1/ws/{session_id}
```

连接时在URL中携带session_id，服务端通过JWT验证身份。

### 3.2 服务端 → 客户端事件

#### `chat.message` — 新消息
```json
{
  "type": "chat.message",
  "data": {
    "id": "msg-3",
    "role": "npc",
    "character_id": "wangdada",
    "text": "你……你怎么找到这个的？",
    "emotion": "shocked",
    "timestamp": "2026-07-05T12:20:00Z"
  }
}
```

#### `stage.changed` — 阶段切换
```json
{
  "type": "stage.changed",
  "data": {
    "from": "act1_investigation",
    "to": "act1_event",
    "stage_name": "第一幕·事件推进",
    "reason": "线索收集完成，自动推进",
    "available_actions": ["talk_to_npc", "examine_scene"],
    "available_characters": ["wangdada", "chengjun"]
  }
}
```

#### `media.play` — 播放媒体指令
```json
{
  "type": "media.play",
  "data": {
    "asset_id": "broadcast_1",
    "type": "story",
    "url": "/storage/audio/broadcast_1.mp3",
    "subtitle_url": "/storage/subtitles/broadcast_1.srt",
    "start_at": 0,
    "volume": 0.7,
    "skip_allowed": true,
    "options": {
      "block_input": true,           // 播放期间是否阻止玩家操作
      "auto_advance": true           // 播放完后是否自动触发下一步
    }
  }
}
```

#### `media.stop` — 停止媒体
```json
{
  "type": "media.stop",
  "data": {
    "asset_id": "bgm_investigation",
    "fade_out": 2.0
  }
}
```

#### `media.bgm_change` — BGM切换
```json
{
  "type": "media.bgm_change",
  "data": {
    "from": "bgm_investigation",
    "to": "bgm_tension",
    "crossfade": 3.0
  }
}
```

#### `clue.unlocked` — 新线索解锁
```json
{
  "type": "clue.unlocked",
  "data": {
    "clue_id": "broken_glass",
    "name": "碎玻璃碴",
    "image_url": "/storage/clues/2.jpg",
    "description": "饭店后门有碎玻璃……",
    "is_key": false
  }
}
```

#### `evidence.discovered` — 新证物发现
```json
{
  "type": "evidence.discovered",
  "data": {
    "evidence_id": "bloody_knife",
    "name": "带血的刀",
    "image_url": "/storage/evidences/knife.jpg"
  }
}
```

#### `npc.state_changed` — 角色状态变化
```json
{
  "type": "npc.state_changed",
  "data": {
    "character_id": "wangdada",
    "emotion": "fear",
    "emotion_description": "王大达脸色发白，额头冒汗",
    "trust_level": 30,
    "tension_level": 80
  }
}
```

#### `event.triggered` — 游戏事件触发
```json
{
  "type": "event.triggered",
  "data": {
    "event_id": "broadcast_1",
    "name": "村长广播",
    "description": "村口的广播突然响起……"
  }
}
```

#### `hint.shown` — 提示推送
```json
{
  "type": "hint.shown",
  "data": {
    "text": "试试问问王大达昨晚听到了什么",
    "remaining_hints": 2
  }
}
```

#### `error` — 错误通知
```json
{
  "type": "error",
  "data": {
    "code": "ACTION_NOT_AVAILABLE",
    "message": "当前阶段不能使用此操作",
    "details": {}
  }
}
```

---

### 3.3 客户端 → 服务端事件

#### `chat.send` — 发送消息
```json
{
  "type": "chat.send",
  "data": {
    "character_id": "wangdada",
    "text": "你昨晚在哪？"
  }
}
```

#### `action.perform` — 执行操作
```json
{
  "type": "action.perform",
  "data": {
    "action": "show_evidence",
    "params": {
      "character_id": "wangdada",
      "evidence_id": "bloody_knife"
    }
  }
}
```

#### `media.ready` — 媒体播放就绪确认
```json
{
  "type": "media.ready",
  "data": {
    "asset_id": "broadcast_1",
    "current_time": 0
  }
}
```

#### `media.ended` — 媒体播放完毕
```json
{
  "type": "media.ended",
  "data": {
    "asset_id": "broadcast_1"
  }
}
```

#### `session.ping` — 保活
```json
{
  "type": "session.ping",
  "data": {}
}
```

---

## 4. 错误码

| HTTP状态码 | 错误码 | 说明 |
|-----------|--------|------|
| 400 | INVALID_ACTION | 不支持的操作类型 |
| 400 | STAGE_NOT_ACCESSIBLE | 当前阶段不允许此操作 |
| 400 | CHARACTER_NOT_AVAILABLE | 该角色当前不在场景中 |
| 400 | EVIDENCE_NOT_DISCOVERED | 证物尚未发现 |
| 400 | CARD_NOT_AVAILABLE | 卡牌不可用或使用次数耗尽 |
| 400 | SUBMISSION_ALREADY_EXISTS | 已提交过最终推理 |
| 404 | SESSION_NOT_FOUND | 会话不存在 |
| 404 | SCRIPT_NOT_FOUND | 剧本包不存在 |
| 409 | SESSION_STATE_CONFLICT | 状态冲突（并发修改） |
| 429 | RATE_LIMITED | 请求过于频繁 |
| 500 | ENGINE_ERROR | 引擎内部错误 |
| 502 | LLM_ERROR | LLM调用失败（临时，可重试） |
| 504 | LLM_TIMEOUT | LLM响应超时（临时，可重试） |
