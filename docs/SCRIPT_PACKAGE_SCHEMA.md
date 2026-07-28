# 剧本包 Schema 规范 (Script Package Schema)

> **这是你编排剧本的核心参考文档。** 每个剧本包是一个文件夹，遵循本规范定义的 YAML Schema。引擎根据这些配置执行游戏。
>
> **当前内容快照：** 仓库现有两个剧本包。
> `script-packages/mp1-two-player/`《两份口供》是双人多人包（`multiplayer.min/max_players: 2`），
> 已支撑双人候选垂直切片从建房到复盘；
> `script-packages/snow-village/`《雪落之前：后门的脚印》是单人 `legacy_single` 切片
> （`max_players: 1`，入口 `return_to_snow_village`），保留为回归基线。
> 本文后半部分为保留字段宽度而展示的旧谋杀故事示例，凡标为“说明性/旧版”的内容都不是任何当前包的真实路径或内容。
>
> **多人字段边界：** `multiplayer_v1` 小节描述当前严格 authoring contract；实际执行边界与
> 变更入口见 [`../openwiki/domain/script-gameplay.md`](../openwiki/domain/script-gameplay.md)。
>
> **多人稳定边界：** 当前只承诺严格双人、按 stage index 顺序执行、以唯一
> `final_judgment` 结束并可供双方复盘的线性契约。导入、发布、建房和冻结快照解码
> 共享同一个 playability 判断；不属于该执行器的合法 legacy 字段会在运行前被拒绝，
> 而不是被静默忽略。完整边界见
> [`PRODUCT_DIRECTION_AND_IMPLEMENTATION_STATUS.md`](PRODUCT_DIRECTION_AND_IMPLEMENTATION_STATUS.md) 第 10.3 节。

---

## 1. 剧本包目录结构

```
script-packages/
├── <script-id>/                     # 剧本包ID：小写+连字符，如 snow-village
│   ├── package.yml                  # ★ 必须：元数据
│   ├── stages/                      # ★ 必须：阶段定义
│   │   ├── _index.yml               # ★ 必须：阶段顺序 + DAG
│   │   ├── <stage-id>.yml           # ★ 必须：每个阶段一个文件
│   │   └── ...
│   ├── characters/                  # ★ 必须：角色定义
│   │   ├── _index.yml               # ★ 必须：角色清单
│   │   ├── <character-id>.yml       # ★ 必须：每个角色一个文件
│   │   └── ...
│   ├── character_scripts/           # ○ 可选：角色专属章节（独立授权）
│   │   └── <character-id>/
│   │       ├── <chapter-id>.md       # YAML frontmatter + Markdown 正文
│   │       └── ...
│   ├── clues/                       # ○ 可选：线索定义
│   │   ├── rounds/                  #   公共线索按轮次
│   │   │   ├── <round-id>.yml
│   │   │   └── ...
│   │   └── personal/                #   保留目录；T-4.2 定义并启用个人线索文件格式
│   │       └── <character-id>.yml
│   ├── evidences/                   # ○ 可选：证物定义
│   │   ├── <evidence-id>.yml
│   │   └── ...
│   ├── scenes/                      # ○ 可选：场景定义
│   │   ├── <scene-id>.yml
│   │   └── ...
│   ├── media/                       # ○ 可选：多媒体定义
│   │   ├── audio.yml
│   │   └── images.yml
│   ├── dm_guide/                    # ○ 可选：DM资料（仅后台可见）
│   │   ├── truth.yml
│   │   ├── stage_notes.yml
│   │   └── performance_guide.yml
│   ├── endings.yml                  # ○ 可选：结局分支
│   └── assets/                      # ○ 可选：剧本包内嵌素材（如有）
│       ├── images/
│       └── audio/
```

> ★ = 必须  ○ = 可选，但推荐

> `clues/personal/` 当前仅保留目录名，不属于 T-2.1 导入契约。个人线索的文件结构、可见性与角色绑定规则将在 T-4.2 内容生产导入阶段定义；在该阶段前，加载器会拒绝该目录内的文件，也不应自行推断文件格式。

### 1.1 人物章节 Markdown

人物章节是独立于 Stage 的授权单位，不是 `characters/<character-id>.yml` 中
`knowledge` 的扩展。文件必须严格放在：

```text
character_scripts/<character-id>/<chapter-id>.md
```

每个文件以 YAML frontmatter 开始，并包含非空 Markdown 正文：

```markdown
---
chapter_id: chapter-01
character_id: zhuosiyuan
order: 1
title: 炉火未熄
visibility: character_only
release:
  type: game_start
stage_min: return_to_snow_village
---

这里是只在本章获准后才能读取的 Markdown 正文。
```

约束如下：

- `chapter_id` 必须与文件名 stem 完全一致，且在整个剧本包内唯一；
- `character_id` 必须与父目录名完全一致，并引用 `characters/` 中已有角色；
- `order` 是非负整数；
- `visibility` 目前只能是 `character_only`；
- `release` 是严格 discriminator mapping：`game_start` 在开局授权；`stage_enter` 仅用于严格多人包，必须携带已有 `stage_id` 并在进入该阶段时授权；`rule` 保留给 legacy 单人规则授权；legacy 单人包会拒绝 `stage_enter`，避免接受单人执行器不会消费的授权声明；
- `stage_min` 可省略；存在时必须引用已有 Stage，但它不替代独立章节授权；严格多人包中它必须与章节映射到的阶段一致；
- 不接受嵌套子目录、非 `.md` 文件、非 UTF-8 文件、缺失 frontmatter 或空正文；
- 章节正文持久化到私有章节表，不自动进入 `script_knowledge` 或当前
  `character_knowledge` RAG 索引；后续只能由服务端依据玩家角色与已解锁章节读取。

### 1.2 `multiplayer_v1` authoring contract

> 以下示例说明多人包的严格 JSON/YAML 形状。导入、发布和建房使用当前严格 playability 规则；冻结快照解码保留相同运行能力校验，但对历史材料 ID 复用和非终局 outcome 材料采用宽容读取，避免追溯淘汰既有房间。

所有 MP-0 authoring 模型继承 `ContractModel`，统一配置为 `strict=True`、`frozen=True`、`extra="forbid"`。未知字段和类型强制转换会被拒绝。

#### 包级多人策略

```yaml
min_players: 2
max_players: 2
character_assignment: required
start_policy: all_players_ready
duplicate_characters: false
```

局部 schema 约束：`min_players`、`max_players` 都必须是 `>= 2` 的整数，且最小人数不能大于最大人数；`character_assignment` 只能是 `required`，`start_policy` 只能是 `all_players_ready`，`duplicate_characters` 只能为 `false`。当前可发布和建房的 `multiplayer_v1` 进一步要求 `min_players == max_players == 2`，且恰好声明两个不重复的 playable character。

#### 阶段组合模型

`MultiplayerStageDefinition` 将角色章节、公共材料、讨论、结算和提示放在同一个 standalone 阶段结构中：

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
    reveal_at: settlement_done
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
hints:
  - id: motive-chain
    levels:
      - "回顾两人的时间线。"
      - "比较已经公开的材料。"
      - "检查无法同时成立的陈述。"
```

局部校验包括：

- `public_materials[].reveal_at` 只能是 `stage_enter`、`all_players_read`、`settlement_done` 或非空 `outcome:<id>`；
- 同一阶段内公共材料 ID 与提示 ID 分别唯一；完整剧本包还要求公共材料 ID 跨阶段唯一；
- 非终局阶段不允许 `outcome:<id>` 公共材料，确保 V2 阶段局部状态可从已到达阶段确定性恢复公共档案；
- `suggested_minutes` 省略时为 `null`，存在时必须大于 0；`close_policy` 默认且只能为 `all_players`；
- 每个提示恰好包含 3 条有序非空文案；
- authoring model 负责局部形状校验；跨文件 material、chapter、outcome 引用由完整剧本包校验统一检查。

#### 阶段结算联合

`StageSettlementDefinition` 以 `mode` 为 discriminator：

| `mode` | 必填字段 | 默认值 |
|---|---|---|
| `none` | `mode` | `default_effect: record_and_continue` |
| `secret_vote` | `settlement_id`、`question`、非空唯一 `options` | `reveal: named_ballots`、`submission_change: forbidden`、`default_effect: record_and_continue` |
| `shared_choice` | `settlement_id`、`question`、非空唯一 `options` | `reveal: outcome_only`、`submission_change: allowed_before_complete`、`default_effect: record_and_continue` |
| `final_judgment` | `settlement_id`、`question`、`answer_mode`、非空唯一 `options` | `reveal: named_ballots`、`submission_change: forbidden`、`default_effect: branch` |

`answer_mode` 只能是 `shared_choice` 或 `individual_secret`。`mode: none` 不能携带 options 等额外字段。unknown mode、空/重复 option、空 question、旧字段名（如 `submission_change_policy`）都会被拒绝。

由剧本包导入、准备发布或创建房间的严格双人剧本版本还必须满足以下 playability 契约：

- `engine.entry_stage` 必须是 stage index 中 `sort_order` 最小的唯一首阶段；存在 `acts` 时，其 `stages` 展平顺序必须与线性 stage 顺序完全一致；`engine.default_ending` 必须省略；
- 每个非终局阶段的 `allowed_transitions` 必须只包含紧邻下一阶段，终局必须为空；阶段跳跃、回退、entry/exit conditions 和未被多人 executor 消费的 legacy capability 必须保持关闭或为空；
- 每个阶段的 `available_characters` 必须恰好覆盖两个 playable character；每个角色章节只能映射一次，第一阶段使用 `release: {type: game_start}`，后续阶段使用与当前阶段一致的 `stage_enter` 和 `stage_min`，不得留下未映射的可玩角色章节；
- 必须包含冻结的 `dm_guide/truth.yml`，且 `truth.case_summary` 必须为非空文本，使 completed room 能为两名参与者分别生成有内容的复盘；
- 阶段序列必须且只能以一个 `final_judgment` 结束，非终局阶段的 `default_effect` 必须为 `record_and_continue`，终局必须为 `branch`；
- `shared_choice` 终局只能使用 `reveal: outcome_only`；
- `ending_by_outcome` 必须显式完整映射每个 option outcome（以及 `individual_secret` 的 tie outcome）到已声明的 `ending.id`；`outcome_id` 与 `ending.id` 无需同名；
- 多人 ending 的 legacy placeholder 只能是 `condition: {type: always}`、空 `on_trigger` 和空 `rating_bonus`，因为多人完成逻辑不执行单人条件、动作或评分加成。

例如：

```yaml
settlement:
  mode: final_judgment
  settlement_id: final-choice
  question: "最终判断是什么？"
  answer_mode: shared_choice
  options:
    - id: accuse-a
      text: "指认甲"
      outcome_id: accuse-a-supported
  ending_by_outcome:
    accuse-a-supported: ending-a-convicted
  reveal: outcome_only
  submission_change: allowed_before_complete
  default_effect: branch
```

这些模型是多人剧本包的导入与运行输入；当前稳定支持的组合是仓库样例所代表的严格双人线性契约。广义 schema 仍可能描述其他人数或 legacy 行为，但这类组合不会被判定为当前多人运行时可玩。

---

## 2. package.yml — 剧本包元数据

```yaml
# 当前 script-packages/snow-village/package.yml
metadata:
  id: "snow-village"
  title: "雪落之前：后门的脚印"
  version: "0.1.0"

info:
  description: "卓司元调查王氏杀猪菜后门异常的首个单人垂直切片。"
  genre: ["悬疑", "互动小说"]
  difficulty: 1
  duration_minutes: 30
  max_players: 1

engine:
  entry_stage: "return_to_snow_village"
```

上例 `snow-village` 没有 `multiplayer`，因此是 `legacy_single` 单人包；仓库中的 `mp1-two-player` 则声明包级多人策略，并使用本节的阶段 authoring contract。广义 loader schema 还允许 `metadata.author`、`metadata.adapter`、`info.min_players`、`visual`、`dm_config`、`guard_rules`、`engine.min_engine_version` 与 `engine.default_ending` 等可选字段；其中 `engine.default_ending` 只属于 legacy 单人执行语义，严格多人包会拒绝它。

---

## 3. stages/_index.yml — 阶段顺序定义

```yaml
# 当前 script-packages/snow-village/stages/_index.yml
stages:
  - id: "return_to_snow_village"
    name: "炉火未熄"
    sort_order: 0
  - id: "investigate_back_alley"
    name: "调查后巷"
    sort_order: 10
  - id: "confront_wangdada"
    name: "没有打开的门"
    sort_order: 20
  - id: "back_door_judgement"
    name: "后门判断"
    sort_order: 30

acts:
  - id: "back_door_footprints"
    name: "后门的脚印"
    stages:
      - "return_to_snow_village"
      - "investigate_back_alley"
      - "confront_wangdada"
      - "back_door_judgement"
```

`stages/_index.yml` 是阶段顺序、展示名和 act 归属的唯一权威来源。索引中的 stage
必须有同 ID 的 YAML 文件，所有 stage YAML 也必须在索引中声明；重复 ID、悬空 act
引用、一个 stage 同属多个 act，或 stage 文件中的 `act_id` 与索引冲突都会拒绝导入。
离开某个 act 最后列出的 stage 后，该 act 才会写入 `completed_acts`。

目标阶段的 `entry_conditions` 会在候选状态上评估：来源阶段及其完成的 act 已可被
`stage_completed` / `act_completed` 观察，但只有入口条件全部满足后才真正提交完成状态并
执行来源阶段退出事件；入口失败时来源阶段仍保持活动状态。

---

## 4. stages/<stage-id>.yml — 单阶段定义

这是你**最常编辑**的文件类型。

> **说明性/旧版示例：** 下列 `act1_investigation` 内容用于展示广义 stage 字段，不存在于当前《雪落之前：后门的脚印》。当前真实阶段以本节前的 `_index.yml` 快照和仓库文件为准。

```yaml
# 说明性/旧版，不是当前包：stages/act1_investigation.yml
# ★ 必须：stage基础信息
id: "act1_investigation"
name: "第一幕·第一轮搜证"
sort_order: 20

# ○ 可选：属于某个幕/本
act_id: "book1"

# ○ 可选：显式允许从本阶段跳转到这些目标
allowed_transitions: ["act1_event"]

# ○ 可选：默认 false；允许跳过中间阶段向前跳转
allow_stage_jump: false

# ○ 可选：默认 false；允许向更早阶段回退
allow_stage_regression: false

# ★ 必须：进入条件（玩家如何到达此阶段）
entry_conditions:
  - type: "stage_completed"
    stage_id: "act1_intro"

# ★ 必须：退出条件（满足任一即退出）
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
        dialog_id: "i_want_to_move_on"
      - type: "time_elapsed"
        minutes: 30

# ★ 必须：玩家在本阶段可做的操作
available_actions:
  - id: "talk_to_npc"
    label: "对话角色"
    description: "与场景中的角色交谈"

  - id: "examine_scene"
    label: "调查场景"
    description: "查看当前场景的可疑位置"

  - id: "show_evidence"
    label: "出示证物"
    description: "向某个角色出示已获得的证物"

  - id: "use_card"
    label: "使用卡牌"
    description: "使用技能卡或道具卡"

  - id: "open_clue_board"
    label: "线索板"
    description: "查看已收集的线索"

  - id: "request_advance"
    label: "请求推进"
    description: "询问DM是否可以进入下一阶段"

# ○ 可选：本阶段开放的场景；缺省为空列表
available_scenes:
  - "crime_scene"                     # 案发现场
  - "village_square"                  # 村口广场

# ○ 可选：本阶段开放的线索轮次；缺省为空列表
available_clue_rounds:
  - "act1_round1"                     # 第一轮公共线索

# ○ 可选：本阶段可对话的角色；缺省为空列表
available_characters:
  - "zhuosiyuan"
  - "cuikaiqiang"
  - "likaiin"
  - "wangqi"
  - "xiaomeng"
  - "chenji"

# ○ 可选：进入本阶段时触发的事件；缺省为空列表
on_stage_entry:
  - action: "dm_narrate"
    text: >
      你走进雪乡村口，白雪覆盖的小路上
      隐约可见一串凌乱的脚印……
  - action: "play_audio"
    asset_id: "bgm_investigation"
    type: "bgm"
    options:
      loop: true
      volume: 0.4
  - action: "unlock_scenes"
    scene_ids: ["crime_scene", "village_square"]
  - action: "unlock_clue_round"
    round_id: "act1_round1"
  - action: "npc_enter_scene"
    character_id: "wangdada"
    scene_id: "village_square"
    dialogue: "哎呀，你们可算来了！"

# ○ 可选：离开本阶段时触发的事件
on_stage_exit:
  - action: "save_checkpoint"
  - action: "play_audio"
    asset_id: "sfx_page_turn"
    type: "sfx"

# ○ 可选：本阶段的媒体触发器
media_triggers:
  - event: "clue_discovered"         # 当前唯一支持的触发事件
    clue_id: "bloody_footprint"       # ★ 必须：已声明的线索 ID
    then:                              # ★ 必须：至少一个合法事件动作
      - action: "play_audio"
        asset_id: "sfx_discovery"
      - action: "npc_emotion"
        character_id: "wangdada"
        state: "nervous_add"

# ○ 可选：本阶段的特殊规则
special_rules:
  prevent_leave_scene: false           # 是否禁止离开当前场景
  auto_save_interval: 60               # 自动保存间隔（秒）
  hint_frequency: "normal"             # normal / frequent / rare
```

---

## 5. characters/_index.yml — 角色清单

> **说明性/旧版示例：** 下列角色清单来自旧谋杀故事，不是当前包。当前包只有可玩角色 `zhuosiyuan`（卓司元）和 NPC `wangdada`（王大达）。

```yaml
# 说明性/旧版，不是当前包：characters/_index.yml
# ★ 必须：角色清单

characters:
  - id: "zhuosiyuan"
    name: "卓司元"
    portrait: "assets/portraits/zhuosiyuan.jpg"
    playable: true                   # 是否可选为玩家角色
    order: 1                          # 显示顺序

  - id: "cuikaiqiang"
    name: "崔铠强"
    portrait: "assets/portraits/cuikaiqiang.jpg"
    playable: true
    order: 2

  - id: "chengjun"
    name: "程俊"
    portrait: "assets/portraits/chengjun.jpg"
    playable: false                  # NPC，不可选
    is_dm_alter_ego: true            # DM的分身（双DM机制）
    order: 100

  # ... 更多角色

# ○ 可选：NPC的"入场"规则
npc_rules:
  default_friendliness: 50           # 初始友好度 0-100
  hostility_on_evidence: -10         # 被出示不利证物时友好度变化
  trust_decay_per_turn: 2            # 每轮不对话信任自然衰减
```

`characters/_index.yml` 必须存在且至少声明一个角色。索引与角色 YAML 按 ID 必须完全
一一对应；索引多项、文件多项或重复 ID 都会在入库前失败。

---

## 6. characters/<character-id>.yml — 单角色定义

> **说明性/旧版示例：** 下列人物知识和反应仅展示字段形状，不是当前 `wangdada.yml` 的内容。

```yaml
# 说明性/旧版，不是当前包：characters/wangdada.yml
# ★ 必须：角色 id 和名称
id: "wangdada"
name: "王大达"
# ○ 可选：角色头像
portrait: "assets/portraits/wangdada.jpg"

# ○ 可选：身份定义；缺省为空对象
identity:
  public: "热情好客的饭店老板"        # 角色卡显示的公众形象
  hidden: "连环杀人案嫌疑人之一"      # 需玩家推理得出的真相
  ultimate_truth: "他不是凶手，但他在掩护真正的凶手"  # 最终真相

# ○ 可选：基础属性；缺省为空对象
attributes:
  age: 45
  gender: "male"
  occupation: "饭店老板"
  residence: "雪乡村口饭店"

# ★ 必须：性格设定
personality:
  summary: "表面大大咧咧、爱吹牛，实则胆小怕事"
  traits:                             # 性格特征（影响AI对话风格）
    - "热情"                          # 招待客人非常热情
    - "碎嘴"                          # 话多，爱唠嗑
    - "胆小"                          # 遇到大事容易慌
    - "护短"                          # 对自己人很保护
  speaking_style: "东北口音，爱用俗语，嗓门大"
  emotional_triggers:                 # 情绪触发点
    - keyword: "命案"
      reaction: "明显紧张，声音变小"
    - keyword: "李白"
      reaction: "眼神闪躲，试图转移话题"

# ★ 必须：知识边界（按阶段定义）
knowledge:
  # 每个阶段角色"知道什么"和"不知道什么"
  stage_act1_intro:
    knows:
      - "饭店最近的经营情况"
      - "村里的八卦传闻"
      - "除夕夜安排"
    doesnt_know:
      - "命案已经发生"                # 此时还未发现尸体
      - "李白已失踪"

  stage_act1_investigation:
    knows:
      - "昨晚听到了奇怪的声音"
      - "李白昨晚没来吃饭"
    doesnt_know:
      - "尸体位置"
      - "凶手身份"

  stage_act2_intro:
    knows:
      - "李白已死"
      - "自己收到过威胁信"
    doesnt_know:
      - "凶手动机"
      - "另一名受害者的关联"

# ○ 可选：面对证物的反应；缺省为空列表
evidence_reactions:
  - evidence_id: "bloody_knife"
    stage_visible: "act1_investigation"
    reaction_text: "这……这是我家厨房的刀！怎么会在那里？！"
    emotional_change:
      shock: +20
      nervous: +30
    state_change:                     # 状态变化
      trust: -10

  - evidence_id: "threatening_letter"
    stage_visible: "act2_intro"
    reaction_text: "（脸色苍白）你也收到了？我以为只有我……"
    emotional_change:
      fear: +40
    dialogue_unlock: "letter_sender"  # 解锁对话分支

# ○ 可选：对话策略
dialogue_strategy:
  avoid_topics:                       # 回避话题
    - "李白"
    - "昨晚十点到十二点在哪"
  lie_about:
    - "昨晚十点到十二点的行踪"        # 会撒谎的事情
  breakdown_conditions:               # 破防条件
    - type: "evidence_shown"
      evidence_id: "alibi_contradiction"
    - type: "player_correct_accusation"
      accusation_id: "hiding_something"
```

---

## 7. clues/ — 线索定义

> **说明性/旧版示例：** 下列 `act1_round1` 不在当前包中。当前线索是 `back-door-first-set` 轮次中的 `clue-back-alley-note`（后巷便签）。

```yaml
# 说明性/旧版，不是当前包：clues/rounds/act1_round1.yml
# 线索轮次定义
round_id: "act1_round1"
name: "第一幕第一轮搜证"
stage_visible: "act1_investigation"    # 轮次归属阶段；不替代 clue.stage_visible

clues:
  - id: "bloody_footprint"
    name: "带血脚印"
    stage_visible: "act1_investigation" # ★ 必须：线索自身的首次可见阶段
    image: "assets/clues/1.jpg"        # 原始线索图
    description: >
      雪地上有一串带血的脚印，从村口饭店方向
      一直延伸到树林深处。
    key_clue: true                      # 是否是关键线索
    importance: 4                       # 1-5 重要性
    related_scene: "village_square"
    related_characters: ["wangdada"]

  - id: "broken_glass"
    name: "碎玻璃碴"
    stage_visible: "act1_investigation" # ★ 必须：即使与轮次相同也要显式声明
    image: "assets/clues/2.jpg"
    description: >
      饭店后门地上有破碎的玻璃杯，
      杯底有微量的白色粉末。
    key_clue: false
    importance: 2
    related_scene: "crime_scene"

  # ... 更多线索
```

---

## 8. scenes/ — 场景定义

> **说明性/旧版示例：** 下列 `crime_scene` 不在当前包中。当前场景是 `restaurant-hall` 与 `back-alley`，唯一热点是 `back-door-traces`。

```yaml
# 说明性/旧版，不是当前包：scenes/crime_scene.yml
id: "crime_scene"
name: "案发现场"
description: "雪乡村口饭店的后院，积雪覆盖的地面上隐约可见挣扎痕迹"

# ★ 必须：场景视觉
visual:
  background: "assets/scenes/crime_scene.jpg"
  ambient_color: "#0d1117"            # 环境光颜色
  parallax_layers: []                 # 视差分层（如有）

# ★ 必须：场景可用条件
available_in_stages:
  - "act1_intro"
  - "act1_investigation"
  - "act1_event"

# ○ 推荐：可交互热点
hotspots:
  - id: "bloody_trail"
    name: "血迹痕迹"
    position: { x: 45, y: 60 }       # 百分比定位
    size: { width: 15, height: 10 }
    cursor: "search"                  # 鼠标样式
    on_click:
      - action: "clue_discover"
        clue_id: "bloody_footprint"
      - action: "dm_narrate"
        text: "你蹲下身仔细观察这些血迹……"

  - id: "back_door"
    name: "饭店后门"
    position: { x: 70, y: 40 }
    size: { width: 12, height: 20 }
    cursor: "search"
    stage_visible: "act1_investigation" # 特定阶段才显示
    on_click:
      - action: "clue_discover"
        clue_id: "broken_glass"

# ○ 可选：场景背景音乐
ambient:
  bgm: "bgm_crime_scene"
  volume: 0.3
```

---

## 9. evidences/ — 证物定义

> **说明性/旧版示例：** 下列 `bloody_knife` 不在当前包中。当前唯一证物是 `evidence-back-door-image`（21:13 后门截图），发现位置为 `back-alley:back-door-traces`。

```yaml
# 说明性/旧版，不是当前包：evidences/bloody_knife.yml
id: "bloody_knife"
name: "带血的刀"
type: "key_evidence"                   # key_evidence / evidence / prop / skill_card

visual:
  image: "assets/evidences/knife.jpg"
  thumbnail: "assets/evidences/knife_thumb.jpg"

# ★ 必须：描述（分表层/深层）
description:
  surface: "一把厨房用的菜刀，刀刃上沾有暗红色痕迹。"
  deep: >
    仔细观察后，你发现刀柄上刻有一个"王"字。
    血迹在刀刃中部较为集中，符合刺入性伤口的特征。

# ★ 必须：发现条件
discovery:
  scene_id: "crime_scene"
  hotspot_id: "back_door"
  stage_visible: "act1_investigation"

# ○ 可选：交互规则；缺省为空对象
interactions:
  can_show_to_npc: true                # 是否能出示给NPC
  can_combine: true                    # 是否能与其他证物组合
  combine_with: ["threatening_letter"]  # 可与"威胁信"组合推理
  can_use_in_final: true               # 是否能用于最终指认

# ○ 可选：出示给不同角色的反应覆盖
npc_reactions:
  - character_id: "wangdada"
    text: "这刀是我家的！但昨晚它明明在厨房里……"
    emotional_impact: { shock: 20, fear: 30 }
```

---

## 10. media/ — 多媒体定义

> **说明性/旧版示例：** 当前 Snow Village 没有 `media/` 目录；下列资源清单只保留为广义 schema 参考。

```yaml
# 说明性/旧版，不是当前包：media/audio.yml
# 所有音频资源定义

audio_assets:
  # BGM类
  - id: "bgm_prologue"
    file: "assets/audio/bgm/prologue.mp3"
    type: "bgm"
    duration_sec: 180
    loop: true
    default_volume: 0.3
    fade_in: 2.0                       # 淡入秒数

  - id: "bgm_investigation"
    file: "assets/audio/bgm/investigation.mp3"
    type: "bgm"
    duration_sec: 240
    loop: true
    default_volume: 0.35

  - id: "bgm_tension"
    file: "assets/audio/bgm/tension.mp3"
    type: "bgm"
    duration_sec: 120
    loop: true
    default_volume: 0.4

  # 剧情音频类
  - id: "broadcast_1"
    file: "assets/audio/story/broadcast_1.mp3"
    type: "story"                      # 剧情音频，不可循环
    duration_sec: 45
    has_subtitle: true
    subtitle_file: "assets/audio/subtitles/broadcast_1.srt"
    skip_allowed: true                 # 玩家可跳过
    trigger_on: "stage_entry"
    trigger_stage: "act1_event"

  - id: "children_song_1"
    file: "assets/audio/story/children_song_1.mp3"
    type: "story"
    duration_sec: 30
    has_subtitle: true
    skip_allowed: false                # 童谣不可跳过（氛围关键）

  # 音效类
  - id: "sfx_discovery"
    file: "assets/audio/sfx/discovery.mp3"
    type: "sfx"
    duration_sec: 2
    default_volume: 0.6

# 图片资源
image_assets:
  - id: "poster_main"
    file: "assets/posters/main.jpg"
    type: "poster"
    usage: ["library_cover", "detail_header"]

  - id: "scene_crime"
    file: "assets/scenes/crime_scene.jpg"
    type: "scene_bg"
    resolution: "1920x1080"
```

---

## 11. dm_guide/ — DM资料（仅后台可见）

> **说明性/旧版示例：** 当前 Snow Village 没有 `dm_guide/` 目录；本节旧谋杀真相、阶段笔记和演绎说明均不是当前包内容。

```yaml
# 说明性/旧版，不是当前包：dm_guide/truth.yml
# ★ 重要：此目录所有文件仅AI DM、Guard Agent、管理员可见
# 不进入玩家Prompt

truth:
  case_summary: >
    李白是雪乡的前任村长，因多年前的一起冤案被程俊杀害。
    程俊化名王大达潜伏在雪乡，在除夕夜制造了连环杀人案……

  murderer: "chengjun"
  victim: "libai"
  motive: "复仇"

  timeline:
    - time: "18:00"
      event: "程俊以王大达身份进入饭店"
      hidden: false
    - time: "20:00"
      event: "李白在厨房与程俊发生争执"
      hidden: true                   # 玩家不可直接看到
    - time: "21:00"
      event: "程俊杀害李白，处理现场"
      hidden: true
    - time: "22:00"
      event: "程俊换装，扮演王大达接待客人"
      hidden: false

  key_evidence_chain:                  # 关键证据链
    - "bloody_knife" → "threatening_letter" → "alibi_hole"
    - "alibi_hole" → "lied_about_location"
    - "lied_about_location" → culprit

  alternative_endings:
    - id: "ending_caught"
      condition: "player_correct_all"
      news_broadcast: "assets/audio/ending/ending_1.mp3"
    - id: "ending_escaped"
      condition: "player_wrong_key"
      news_broadcast: "assets/audio/ending/ending_2.mp3"
```

```yaml
# 说明性/旧版，不是当前包：dm_guide/stage_notes.yml
# 带本要点：每个阶段的DM注意事项

stage_notes:
  - stage_id: "act1_intro"
    dm_behavior: "正常、热情的开场"
    notes: >
      DM以李白身份出现，自然发本。
      注意分发角色剧本后，趁玩家阅读时偷偷换人。
      确保不被玩家发现同一个DM在同框出现。

    atmosphere: "轻松、过年氛围"
    key_moments:                       # 关键节点
      - action: "player_reading_done"
        dm_action: "提醒玩家收起剧本，开始第一幕"

  - stage_id: "act1_event"
    dm_behavior: "广播后由谄媚→凶恶切换"
    notes: >
      播放村长广播后，DM应该瞬间变脸。
      从热情老板变成阴森变态。

    atmosphere: "紧张、压迫感"
    prop_usage:                        # 道具使用
      - "围裙（暗示厨师的工具）"
      - "面具（第二幕使用）"

  - stage_id: "fake_final"
    dm_behavior: "假复盘，泰然自若"
    notes: >
      假装这是最终复盘，给玩家发放问卷。
      暗中用手机录音玩家的讨论。
      选择戒备心低的玩家回答问题。

    trap_mechanics:
      - "录音玩家的推理过程"
      - "假借问卷收集玩家签名"
      - "小号在群里发合照"

  - stage_id: "true_final"
    dm_behavior: "完全释放，越变态越好"
    notes: >
      不再隐藏程俊的身份。
      呈现精神失常的状态。
      播放之前的录音。
      根据玩家选择播放不同的新闻结局。

    atmosphere: "全黑，只有手机屏幕光"
```

```yaml
# 说明性/旧版，不是当前包：dm_guide/performance_guide.yml
# 演绎要点

performance:
  dm_split_personality:
    phase_1:
      character: "李白（正常DM）"
      actor: "DM1"
      traits: ["热情", "专业", "稍微有点话痨"]

    phase_2:
      character: "王大达（DM扮演）"
      actor: "DM2"
      traits: ["谄媚", "碎嘴", "东北口音"]
      pre_broadcast: "正常的饭店老板"
      post_broadcast: "恐惧但强装镇定"

    phase_3:
      character: "王小达（戴面具）"
      actor: "DM2"
      traits: ["神秘", "压低声音说话"]

    phase_4:
      character: "崔鹏（假复盘）"
      actor: "DM2"
      traits: ["专业", "泰然自若", "套话"]

    phase_5:
      character: "程俊（真身）"
      actor: "DM2"
      traits: ["阴森", "变态", "控制狂", "享受玩家的恐惧"]

  key_dialogue_lines:
    - phase: "act1_intro"
      line: "欢迎各位来到雪乡！"
      emotion: "热情"

    - phase: "true_final"
      line: "你们刚刚所说的一切……我都录了音。"
      emotion: "阴森冷笑"
```

---

## 12. endings.yml — 结局分支

> **当前事实：** `script-packages/snow-village/endings.yml` 是 `endings: []`。最终阶段目前通过 `special_rules.judgement` 和 Final Submission API 评分，不依赖本节的旧结局条目。下列内容仅为说明性/旧版 schema 示例。

```yaml
# 说明性/旧版，不是当前包：endings.yml
# 结局分支定义

endings:
  - id: "truth_revealed"
    name: "真相大白"
    condition:                         # 触发条件
      type: "all"
      conditions:
        - type: "submission_correct"
          field: "suspect"
          value: "chengjun"
        - type: "submission_correct"
          field: "motive"
          value: "revenge"
        - type: "key_evidence_used"
          min_count: 3

    on_trigger:
      - action: "play_audio"
        asset_id: "ending_bgm_true"
      - action: "dm_narrate"
        text: "你终于拼凑出了全部的真相……"
      - action: "play_audio"
        asset_id: "ending_1"
      - action: "show_truth_summary"
      - action: "transition_to"
        stage_id: "epilogue"

    outcome_text: >
      程俊被警方逮捕。雪乡的雪依旧在下，
      但这个除夕夜，没有人能真正安心过年……

    rating_bonus:                     # 评分加成
      base_score: 100
      score_breakdown:
        correct_suspect: 30
        correct_motive: 25
        key_evidence_count: 25
        deduction_chain: 20

  - id: "murderer_escaped"
    name: "真凶逃脱"
    condition:
      type: "any"
      conditions:
        - type: "submission_incorrect"
          field: "suspect"
        - type: "submission_incorrect"
          field: "motive"

    on_trigger:
      - action: "play_audio"
        asset_id: "ending_bgm_dark"
      - action: "dm_narrate"
        text: "你以为找到了答案，但真相远比你想的更复杂……"
      - action: "play_audio"
        asset_id: "ending_2"
      - action: "transition_to"
        stage_id: "epilogue"

    outcome_text: >
      真凶消失在雪夜中，这个案子成了悬案。
      但雪乡的恐怖传说，还在继续……
```

---

## 13. Schema验证规则（引擎侧）

导入器对已经建模的 YAML object（包括 `dm_guide/` 的三个支持文件）使用 `extra="forbid"`，未知字段会被拒绝而不是被忽略。条件、事件、热点和规则载荷仍以 JSON object 原样保留，但它们的列表项类型、动作名和已实现引用会在导入边界继续校验；尚未建模的个人线索格式不在当前导入范围内。

下面的 `validation_rules` 是本规范对引擎行为的说明清单，不是 `package.yml` 中允许的
字段，不能复制进剧本包。实际导入还执行这些边界：ZIP 最多 2048 个文件、单文件
64 MiB、总展开 512 MiB、压缩比 200；单个 YAML 最多 1 MiB、深度 64、节点 50000，
并拒绝 alias、重复成员、路径穿越、符号链接和非普通文件。

```yaml
# 引擎在 import 时自动验证以下规则
validation_rules:
  package_yml:
    required_fields: ["metadata.id", "metadata.title", "engine.entry_stage"]
    field_types:
      "metadata.id": "string, lowercase, hyphens"
      "info.difficulty": "integer 1-5"

  stage:
    required_fields: ["id", "name", "entry_conditions", "exit_conditions", "available_actions"]
    index_file_parity: true                # stages/_index.yml 与 stage YAML 必须一一对应
    transition_policy_valid: true          # 默认仅允许相邻前进；显式配置才可跳跃/回退
    condition_references_valid: true       # 检查引用的stage_id/clue_id/char_id是否存在
    event_actions_valid: true              # 检查action名称是否引擎支持
    event_payloads_valid: true             # 按 action 校验必需字段、类型和实体引用

  character:
    required_fields: ["id", "name", "personality.summary", "knowledge"]
    index_file_parity: true                # characters/_index.yml 与角色 YAML 必须一一对应
    stage_knowledge_coverage:              # 检查每个stage是否都有知识定义
      warn_if_missing: true

  clue:
    required_fields: ["id", "name", "description", "stage_visible"]
    image_exists: true                     # 检查引用的图片文件是否存在

  evidence:
    required_fields: ["id", "name", "description.surface", "discovery.scene_id"]
    allowed_types: ["key_evidence", "evidence", "prop", "skill_card"]
    npc_reactions_valid: true              # 检查引用的character_id是否存在

  scene:
    required_fields: ["id", "name", "visual", "available_in_stages"]
    stage_references_valid: true
```

---

## 14. 剧本编排的最佳实践

```
DO:
├─ stages/_index.yml 中预留足够的排序间隔(10)，方便插入新阶段
├─ 每个角色的知识边界按stage精确切割，越细越好
├─ 关键线索标记 key_clue: true，引擎自动追踪
├─ 假结局 stage 标记 meta.is_fake: true
├─ 音频附带字幕，适配静音/无障碍场景
└─ 条件使用嵌套逻辑(type: any/all)而非平铺

DON'T:
├─ 不要跨stage引用尚未出现的角色
├─ 不要在knowledge.doesnt_know里写得太细——引擎自动过滤
├─ 不要在一个yml里塞超过20个条件（拆成多个阶段）
├─ 不要把dm_guide的内容放在玩家可见的clues/中
└─ 不要修改engine目录的代码来适配剧本——用yml表达
```
