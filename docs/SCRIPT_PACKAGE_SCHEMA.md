# 剧本包 Schema 规范 (Script Package Schema)

> **这是你编排剧本的核心参考文档。** 每个剧本包是一个文件夹，遵循本规范定义的 YAML Schema。引擎根据这些配置执行游戏。

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
│   ├── clues/                       # ○ 可选：线索定义
│   │   ├── rounds/                  #   公共线索按轮次
│   │   │   ├── <round-id>.yml
│   │   │   └── ...
│   │   └── personal/                #   个人线索
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

---

## 2. package.yml — 剧本包元数据

```yaml
# script-packages/snow-village/package.yml
# ★ 必须：剧本包身份信息
metadata:
  id: "snow-village"                  # 唯一标识，用于script_packages表
  title: "雪乡连环杀人事件"             # 展示名
  version: "1.0.0"                    # 语义化版本
  author: "XXX剧本工作室"              # 剧本原作者
  adapter: "你的名字"                  # AI版本改编者

# ○ 推荐：基础信息
info:
  description: >
    雪乡，一个被大雪覆盖的东北村庄。
    新年将至，村子里却接连发生命案……
  genre: ["悬疑", "推理", "惊悚"]      # 标签
  difficulty: 3                        # 1-5 难度
  duration_minutes: 120                # 推荐时长
  min_players: 1                       # 最少真人玩家数
  max_players: 1                       # 目前单人，后续可扩

# ○ 推荐：视觉效果配置
visual:
  poster: "assets/posters/main.jpg"   # 剧本库封面
  logo: null                           # 可选Logo
  theme_color: "#1a1a2e"              # 主题色（影响前端UI）
  font: "serif"                       # 字体风格

# ○ 推荐：DM风格配置
dm_config:
  style: "immersive"                   # immersive / friendly / dramatic
  voice_actor: "default"               # TTS音色
  opening_speech: >
    各位玩家，欢迎来到雪乡。
    今天是除夕夜，村子里张灯结彩，
    但一场命案正在悄然发生……

# ○ 可选：Guard Agent附加规则
guard_rules:
  extra_forbidden_topics: []           # 额外禁止话题
  character_knowledge_strictness: "normal"  # normal / strict / relaxed

# ★ 必须：引擎加载所需
engine:
  min_engine_version: "1.0.0"
  entry_stage: "prologue"              # 游戏从哪个stage开始
  default_ending: "truth_revealed"     # 默认结局ID
```

---

## 3. stages/_index.yml — 阶段顺序定义

```yaml
# script-packages/snow-village/stages/_index.yml
# ★ 必须：定义所有阶段及其顺序

stages:
  - id: "prologue"                     # 阶段ID，全局唯一
    name: "序章"                       # 展示名
    sort_order: 0                      # 排序，进一不可逆
  
  - id: "act1_intro"
    name: "第一幕·开场"
    sort_order: 10
  
  - id: "act1_investigation"
    name: "第一幕·第一轮搜证"
    sort_order: 20
  
  - id: "act1_event"
    name: "第一幕·事件推进"
    sort_order: 30
  
  - id: "act1_confrontation"
    name: "第一幕·对峙"
    sort_order: 40
  
  - id: "act2_intro"
    name: "第二幕·开启"
    sort_order: 50
  
  - id: "act2_investigation"
    name: "第二幕·搜证"
    sort_order: 60
  
  - id: "fake_final"                   # ★ 支持假结局
    name: "假·最终推理"
    sort_order: 70
    meta:
      is_fake: true                    # 标记为假结局
  
  - id: "act3_online"
    name: "线上剧本"
    sort_order: 80
  
  - id: "true_final"
    name: "真相揭示"
    sort_order: 90
  
  - id: "epilogue"
    name: "复盘"
    sort_order: 100

# ○ 可选：定义阶段组（如第一本/第二本）
acts:
  - id: "book1"
    name: "第一本"
    stages: ["prologue", "act1_intro", "act1_investigation", "act1_event", "act1_confrontation"]
  
  - id: "book2"
    name: "第二本"
    stages: ["act2_intro", "act2_investigation", "fake_final"]
  
  - id: "online"
    name: "线上篇"
    stages: ["act3_online", "true_final", "epilogue"]
```

---

## 4. stages/<stage-id>.yml — 单阶段定义

这是你**最常编辑**的文件类型。

```yaml
# script-packages/snow-village/stages/act1_investigation.yml
# ★ 必须：stage基础信息
id: "act1_investigation"
name: "第一幕·第一轮搜证"
sort_order: 20

# ○ 可选：属于某个幕/本
act_id: "book1"

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

# ★ 必须：本阶段开放的场景
available_scenes:
  - "crime_scene"                     # 案发现场
  - "village_square"                  # 村口广场

# ★ 必须：本阶段开放的线索轮次
available_clue_rounds:
  - "act1_round1"                     # 第一轮公共线索

# ★ 必须：本阶段可对话的角色
available_characters:
  - "zhuosiyuan"
  - "cuikaiqiang"
  - "likaiin"
  - "wangqi"
  - "xiaomeng"
  - "chenji"

# ★ 必须：进入本阶段时触发的事件
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
  - event: "clue_discovered"
    clue_id: "bloody_footprint"
    then:
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

```yaml
# script-packages/snow-village/characters/_index.yml
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

---

## 6. characters/<character-id>.yml — 单角色定义

```yaml
# script-packages/snow-village/characters/wangdada.yml
# ★ 必须：角色信息
id: "wangdada"
name: "王大达"
portrait: "assets/portraits/wangdada.jpg"

# ★ 必须：身份定义
identity:
  public: "热情好客的饭店老板"        # 角色卡显示的公众形象
  hidden: "连环杀人案嫌疑人之一"      # 需玩家推理得出的真相
  ultimate_truth: "他不是凶手，但他在掩护真正的凶手"  # 最终真相

# ★ 必须：基础属性
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

# ★ 必须：面对证物的反应
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

```yaml
# script-packages/snow-village/clues/rounds/act1_round1.yml
# 线索轮次定义
round_id: "act1_round1"
name: "第一幕第一轮搜证"
stage_visible: "act1_investigation"    # 在哪个stage开放

clues:
  - id: "bloody_footprint"
    name: "带血脚印"
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

```yaml
# script-packages/snow-village/scenes/crime_scene.yml
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

```yaml
# script-packages/snow-village/evidences/bloody_knife.yml
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

# ★ 必须：交互规则
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

```yaml
# script-packages/snow-village/media/audio.yml
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

```yaml
# script-packages/snow-village/dm_guide/truth.yml
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
# script-packages/snow-village/dm_guide/stage_notes.yml
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
# script-packages/snow-village/dm_guide/performance_guide.yml
# 演绎要点

performance:
  dm_split_personality:
    phase_1: "李白（正常DM）"
      actor: "DM1"
      traits: ["热情", "专业", "稍微有点话痨"]
    
    phase_2: "王大达（DM扮演）"
      actor: "DM2"
      traits: ["谄媚", "碎嘴", "东北口音"]
      pre_broadcast: "正常的饭店老板"
      post_broadcast: "恐惧但强装镇定"
    
    phase_3: "王小达（戴面具）"
      actor: "DM2"
      traits: ["神秘", "压低声音说话"]
    
    phase_4: "崔鹏（假复盘）"
      actor: "DM2"
      traits: ["专业", "泰然自若", "套话"]
    
    phase_5: "程俊（真身）"
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

```yaml
# script-packages/snow-village/endings.yml
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
    condition_references_valid: true       # 检查引用的stage_id/clue_id/char_id是否存在
    event_actions_valid: true              # 检查action名称是否引擎支持
  
  character:
    required_fields: ["id", "name", "personality.summary", "knowledge"]
    stage_knowledge_coverage:              # 检查每个stage是否都有知识定义
      warn_if_missing: true
  
  clue:
    required_fields: ["id", "name", "description", "stage_visible"]
    image_exists: true                     # 检查引用的图片文件是否存在
  
  evidence:
    required_fields: ["id", "name", "description.surface", "discovery.scene_id"]
    npc_reactions_valid: true              # 检查引用的character_id是否存在
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
