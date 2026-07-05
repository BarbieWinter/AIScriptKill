# 条件 DSL 参考 (Condition DSL Reference)

> 引擎内置的通用条件表达式语言。所有剧本共享同一套条件类型，用于定义阶段推进、事件触发、结局分支等逻辑。

---

## 1. 条件 DSL 概述

条件 DSL 是 YAML 内嵌的树形表达式结构，每个条件是一个对象：

```yaml
condition:
  type: "condition_type"    # 条件类型
  param1: value1            # 条件参数
  param2: value2
```

条件支持嵌套组合：

```yaml
type: "any"                 # OR
conditions:                 # 子条件列表
  - type: "all"             # AND
    conditions: [...]
  - type: "not"             # NOT
    condition: {...}
```

所有条件最终求值为 `true` 或 `false`。

---

## 2. 条件类型完整列表

### 2.1 游戏进度条件

#### `stage_completed`
玩家是否已通过某个阶段。

```yaml
type: "stage_completed"
stage_id: "act1_intro"          # 必须已完成的阶段ID
```

#### `stage_reached`
玩家是否已达到某个阶段。

```yaml
type: "stage_reached"
stage_id: "act2_intro"          # 至少已经到达的阶段
```

#### `act_completed`
玩家是否已完成某个幕/本。

```yaml
type: "act_completed"
act_id: "book1"                 # 幕/本ID
```

---

### 2.2 线索和证物条件

#### `clues_discovered`
已发现的线索数量条件。

```yaml
type: "clues_discovered"
in_round: "act1_round1"         # 可选：指定线索轮次
in_scene: "crime_scene"         # 可选：指定场景
min_count: 3                    # 至少发现N个
max_count: 10                   # 可选：至多N个
exact_count: 5                  # 可选：恰好N个
key_only: true                  # 可选：只计关键线索
```

#### `clue_discovered`
具体某个线索是否已发现。

```yaml
type: "clue_discovered"
clue_id: "bloody_footprint"     # 线索ID
```

#### `evidence_found`
具体证物是否已发现。

```yaml
type: "evidence_found"
evidence_id: "bloody_knife"
```

#### `evidence_shown_to_npc`
某个证物是否已出示给某个角色。

```yaml
type: "evidence_shown_to_npc"
evidence_id: "bloody_knife"
character_id: "wangdada"
```

---

### 2.3 对话条件

#### `character_talked_to`
是否与某角色对话过。

```yaml
type: "character_talked_to"
character_id: "wangdada"
min_count: 3                    # 可选：至少对话N次
```

#### `dialog_triggered`
特定对话是否已触发。

```yaml
type: "dialog_triggered"
dialog_id: "letter_sender"      # 对话分支ID
```

#### `player_said_keyword`
玩家是否说出了某个关键词。

```yaml
type: "player_said_keyword"
keyword: "李白"                  # 关键词
case_sensitive: false           # 可选：是否大小写敏感
```

#### `npc_state_reached`
角色是否达到了某个情绪状态。

```yaml
type: "npc_state_reached"
character_id: "wangdada"
state: "nervous"                # 状态名
threshold: 50                   # 可选：阈值（用于数值型状态）
comparison: "gte"               # gte/gt/lte/lt/eq
```

---

### 2.4 玩家行为条件

#### `player_action_performed`
玩家是否执行了某个操作。

```yaml
type: "player_action_performed"
action_id: "use_card"           # 操作ID
target: null                    # 可选：操作对象
```

#### `player_requested`
玩家是否主动请求了推进。

```yaml
type: "player_requested"
dialog_id: "i_want_to_move_on"   # 可选：具体的请求ID
```

#### `player_used_card`
玩家是否使用了卡牌。

```yaml
type: "player_used_card"
card_id: "interrogation_card"   # 可选：具体卡牌ID
card_type: "skill"              # 可选：skill / prop
```

---

### 2.5 时间条件

#### `time_elapsed`
距阶段开始是否已过一定时间。

```yaml
type: "time_elapsed"
minutes: 20                     # 至少N分钟
since_stage_entry: true         # 可选：仅从本阶段开始计时
```

#### `real_time_reached`
是否到达了真实世界的特定时间点。

```yaml
type: "real_time_reached"
time: "2026-07-05T21:00:00+08:00"  # 特定时间
```

---

### 2.6 推理提交条件

#### `submission_correct`
玩家提交的答案是否正确。

```yaml
type: "submission_correct"
field: "suspect"                # 提交的字段名
value: "chengjun"               # 正确值
```

#### `submission_incorrect`
玩家提交的答案是否错误。

```yaml
type: "submission_incorrect"
field: "suspect"                # 提交的字段名
value: "wangdada"               # 错误值（可选，不指定则只要不正确即可）
```

#### `key_evidence_used`
关键证据是否被提交。

```yaml
type: "key_evidence_used"
min_count: 3                    # 至少使用N个关键证据
evidence_ids: []                # 可选：指定必须使用的证据
```

#### `deduction_chain_complete`
推理链是否完整。

```yaml
type: "deduction_chain_complete"
chain_id: "main"                # 推理链ID（定义在truth.yml中）
```

---

### 2.7 事件条件

#### `event_triggered`
某事件是否已触发。

```yaml
type: "event_triggered"
event_id: "broadcast_1"         # 事件ID
```

#### `event_not_triggered`
某事件是否尚未触发。

```yaml
type: "event_not_triggered"
event_id: "true_final_reveal"
```

---

### 2.8 游戏全局条件

#### `session_count`
玩家在本会话中的某些计数。

```yaml
type: "session_count"
counter: "wrong_submissions"    # 计数类型
min: 2                          # 至少N次
max: 5                          # 至多N次
```

#### `is_first_play`
是否是首次游玩此剧本。

```yaml
type: "is_first_play"
```

#### `hint_count_used`
已使用的提示次数。

```yaml
type: "hint_count_used"
min: 1                          # 至少使用了N次提示
max: 3
```

---

## 3. 逻辑组合条件

### `all` — AND
所有子条件必须为真。

```yaml
type: "all"
conditions:
  - type: "clues_discovered"
    in_round: "act1_round1"
    min_count: 3
  - type: "character_talked_to"
    character_id: "wangdada"
  - type: "time_elapsed"
    minutes: 15
```

### `any` — OR
至少一个子条件为真。

```yaml
type: "any"
conditions:
  - type: "clues_discovered"
    in_round: "act1_round1"
    min_count: 5
  - type: "time_elapsed"
    minutes: 30
  - type: "player_requested"
    dialog_id: "move_on"
```

### `not` — NOT
子条件为假时成立。

```yaml
type: "not"
condition:
  type: "stage_completed"
  stage_id: "act2_intro"
```

### `count` — N-of-M
至少N个子条件为真。

```yaml
type: "count"
min: 2
conditions:
  - type: "character_talked_to"
    character_id: "zhuosiyuan"
  - type: "character_talked_to"
    character_id: "cuikaiqiang"
  - type: "character_talked_to"
    character_id: "likaiin"
```

### `always` — 恒真
永远为真。

```yaml
type: "always"
```

### `never` — 恒假
永远为假（用于调试/封锁）。

```yaml
type: "never"
```

---

## 4. 条件使用场景

### 场景1：阶段退出条件

```yaml
# stages/act1_investigation.yml
exit_conditions:
  - type: "any"
    conditions:
      - type: "all"
        conditions:
          - type: "clues_discovered"
            in_round: "act1_round1"
            min_count: 3
          - type: "character_talked_to"
            character_id: "wangdada"
      - type: "player_requested"
        dialog_id: "request_advance"
      - type: "time_elapsed"
        minutes: 30
```

### 场景2：事件触发条件

```yaml
# stages/act1_event.yml
on_clue_discovered:
  - condition:
      type: "all"
      conditions:
        - type: "clue_discovered"
          clue_id: "bloody_footprint"
        - type: "character_talked_to"
          character_id: "wangdada"
          min_count: 2
    then:
      - action: "play_audio"
        asset_id: "broadcast_1"
      - action: "npc_emotion"
        character_id: "wangdada"
        state: "fear"
```

### 场景3：结局分支条件

```yaml
# endings.yml
endings:
  - id: "truth_revealed"
    condition:
      type: "all"
      conditions:
        - type: "submission_correct"
          field: "suspect"
          value: "chengjun"
        - type: "key_evidence_used"
          min_count: 3
  
  - id: "murderer_escaped"
    condition:
      type: "any"
      conditions:
        - type: "submission_incorrect"
          field: "suspect"
        - type: "submission_incorrect"
          field: "motive"
```

### 场景4：NPC状态变化条件

```yaml
# characters/wangdada.yml
evidence_reactions:
  - evidence_id: "bloody_knife"
    condition:                                    # 附加条件
      type: "all"
      conditions:
        - type: "time_elapsed"
          minutes: 10
        - type: "not"
          condition:
            type: "npc_state_reached"
            character_id: "wangdada"
            state: "panic"
    reaction_text: "这不可能……"
    state_change:
      fear: 50
```

---

## 5. 条件评估机制（理解有助于调试）

```
┌─────────────────────────────────────────────────────────┐
│                   Condition Evaluator                     │
│                                                          │
│  1. 接收条件树 + 当前 GameState                           │
│                                                          │
│  2. 深度优先遍历                                          │
│     ├─ 叶子节点：调用对应评估器                             │
│     │   例: clues_discovered → 查state.unlocked_clues     │
│     ├─ 组合节点：递归评估子条件                             │
│     │   例: all → 全部true = 整体true                      │
│     └─ 短路优化                                           │
│         all: 遇到false即返回false                          │
│         any: 遇到true即返回true                            │
│                                                          │
│  3. 返回 boolean                                          │
│                                                          │
│  4. 结果缓存到 state.condition_cache                      │
│     ├─ 同一session中重复条件不重复评估                      │
│     └─ 缓存key = hash(条件树 + 相关state片段)              │
└─────────────────────────────────────────────────────────┘
```

---

## 6. 条件编写最佳实践

```
DO:
├─ 使用 any/or 包裹多个宽松条件，让玩家有多种方式推进
├─ 大型条件树用缩进和注释保持可读性
├─ 用 count 而非 all 做"至少N个角色对话过"的判断
├─ 关键路径条件加注释说明意图
├─ 调试时先用 always 测试阶段是否可进入

DON'T:
├─ 不要写超过5层的嵌套条件（重构为中间阶段）
├─ 不要把条件分散到多个yml中相互引用
├─ 不要在exit_conditions里用 time_elapsed 作为唯一条件
│  （会让玩家觉得被时间赶着走）
├─ 不要依赖条件评估的顺序——它们是声明式的，不是命令式的
└─ 不要在条件中使用硬编码的玩家ID（引擎自动注入session上下文）
```

---

## 7. 条件调试模式

引擎支持条件调试输出：

```yaml
# 后台测试沙盒开启条件追踪
debug:
  condition_tracing: true          # 输出每条条件的评估结果
  force_conditions:                # 手动覆盖条件结果（测试用）
    time_elapsed: always_true
```

输出示例：
```
[Condition Trace] stage_exit_check for act1_investigation:
  ├─ any: FALSE
  │  ├─ all: FALSE
  │  │  ├─ clues_discovered(act1_round1, min=3): TRUE (5 found)
  │  │  └─ character_talked_to(wangdada): FALSE (not talked yet)
  │  ├─ player_requested: FALSE
  │  └─ time_elapsed(min=30): FALSE (elapsed 12min)
  └─ Result: FALSE (stay in stage)
```
