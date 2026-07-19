# 剧本与玩法领域

## 产品边界

核心领域是固定剧本的 AI 互动悬疑。`/doc/剧本系统设计.md` 描述的原则仍有效：高质量谜题和事实边界是确定性的，AI 负责受控表达和沉浸感。

AI 可以：

- 扮演当前阶段允许的 NPC。
- 在角色知识和会话已授权材料范围内自然回答。
- 使用经过阶段/角色/线索权限过滤的 RAG 片段。

AI 不应：

- 改变正确判断、动机或关键证据。
- 发明主线事实。
- 泄露未来阶段、其他角色私有材料、DM 指引或未发现内容。
- 决定解锁、阶段切换、评分或状态 patch；这些由 YAML/StateGraph 确定。

这一边界由剧本包 schema、条件/事件运行时、API 投影、RAG permissions 和 NPC 本地输出过滤共同实现。

## 主要领域概念

### 剧本包

剧本包是内容单元。后端支持 zip 导入，也支持 `load_package_directory()` 复用同一加载流程。归档必须恰好有一个 `package.yml`，并通过 strict Pydantic 模型、引用校验和资产校验。

必需内容：

- `package.yml`：`metadata.id/title/version` 和 `engine.entry_stage`。
- `stages/`：至少一个阶段 YAML。
- `characters/`：至少一个角色 YAML。

可选且 loader 已支持：

- `stages/_index.yml`：阶段/幕顺序。
- `characters/_index.yml`：可玩性和排序。
- `character_scripts/<character-id>/<chapter-id>.md`：严格 frontmatter 的角色私有 Markdown 章节。
- `clues/rounds/*.yml`、`evidences/*.yml`、`scenes/*.yml`。
- `media/*.yml`。
- `endings.yml`。
- `dm_guide/*.yml`，只写入服务端私有表，不进入公开 package config。
- `assets/`，可上传私有 Storage，并把 YAML 本地路径重写为 `storage://` 定位符。

`engine/core/package_records.py` 将内容转换为 package/stage/character/chapter/clue/evidence/scene/media/ending 记录。`runtime_package_repository.py` 可从已发布规范化数据库行重建同一 `ScriptPackageImport` 给生产 StateGraph 使用。

### 阶段和动作

阶段是受控推进单元，定义：

- entry/exit conditions。
- available actions/characters/scenes。
- stage-entry、clue-discovered 等事件。
- 可选 judgment 等 special rules。

生产 REST action 已连接 `LangGraphRuntimeActionExecutor`，不再使用旧固定 action mapper。`runtime_action_mappers.py` 把 REST 载荷编码为 core action target：

- `talk_to_npc` -> character id + player text。
- `examine_scene` -> scene/hotspot target。
- `show_evidence` -> `evidence_id:character_id`。
- `use_card`、`open_clue_board`、`request_advance` -> 各自窄 target。

`ScriptEngine` 校验当前阶段是否允许 action/target，执行 YAML 事件和条件，写入 checkpoint，再投影 session/chat/discoveries。非法动作返回稳定错误码，不会静默 no-op。

### 角色和 NPC

角色可为玩家、NPC 或 DM alter ego。导入记录包含可玩性、DM 标记、排序、identity、personality、分阶段 knowledge、evidence reactions 和 dialogue strategy。

生产 NPC 路径位于 `engine/agents/npc_agent.py`：

- 配置完整时调用 OpenAI-compatible Chat Completions。
- 只把当前角色、阶段、包内已授权 knowledge、有限历史和 `RagRetriever` 返回的授权片段放入 prompt。
- 证物 reaction 只有在证物已查看、已向该 NPC 出示、阶段和条件均满足时才进入允许事实。
- provider/RAG 失败、配置不完整、输出为空/过长、出现 forbidden term 或未授权时间值时，返回确定性 fallback：`我只能说自己亲眼见过、亲耳听到的，没把握的事不能乱讲。`

这已不是固定“王大达风格”占位回复，但本地过滤只覆盖明确约束，不应被描述为通用语义证明或已实现 AI-DM/多人裁判。

### 线索和证据

- 线索存储于 `script_clues`，通过 `session_discoveries(entity_type='clue')` 解锁。
- 证据存储于 `script_evidences`，发现状态也在 discoveries；`POST .../evidences/{id}/viewed` 将其从 `unlocked` 单调升级为 `viewed`。
- 向 NPC 出示证据记录于 GameState/session 投影；NPC evidence reaction 还要求证据已查看。

浏览器不能直接读表。FastAPI 结合 session discovery、阶段和角色做授权和字段投影。

### 场景、热点和媒体

场景 YAML 包含背景、公开描述、视觉元数据和热点。当前真实后端已实现 `GET .../presentation`：从当前已发布场景白名单返回 id/name/description/ambient color、浏览器安全背景 URL及有序 public hotspots。

热点只公开 id、label、x/y、width/height；private/DM-only 项和 `on_click` 规则不会返回。前端点击后提交 scene/hotspot id，由服务端 StateGraph 执行 `clue_discover`、`evidence_discover`、`dm_narrate` 等 YAML 事件。

媒体 schema 和导入已支持 `bgm`、`story`、`sfx`、`voice`、`image`、`video`。私有 Storage 的 `storage://` 定位符不是浏览器 URL；签名 URL/代理下载和完整 media orchestrator 仍未实现。

### 人物章节

人物章节采用：

```text
character_scripts/<character-id>/<chapter-id>.md
```

文件必须是 UTF-8，包含严格 YAML frontmatter 和非空 Markdown 正文；路径中的 character/chapter id 必须与 frontmatter 一致。frontmatter 声明：

- `character_id`、`chapter_id`、`order`、`title`。
- 固定 `visibility: character_only`。
- `release.type: game_start`，或 `release.type: rule` + `rule_id`。
- 可选 `stage_min`。

导入写入 service-role-only 的 `script_character_chapters`。开局事件或 `unlock_character_chapter` 只会为当前玩家角色发放匹配章节，并在 `session_discoveries(entity_type='character_chapter')` 记录 `unlocked`。list/read API 同时要求：

1. session 可访问；
2. chapter 属于 `session.player_character_id`；
3. 当前 session 有 `unlocked` 或 `viewed` discovery。

读取正文后状态单调升级为 `viewed`。章节正文有意不进入普通 `script_knowledge` chunking，因此当前不能声称 RAG 会检索人物章节全文。

### Judgment、结局和复盘

当前阶段可在 `special_rules.judgement` 中声明 question、options 和 `correct_option`。presentation 只返回 question/options；提交端点在服务端读取正确 option。

当前评分 helper 是确定性的：匹配正确 option 得 100，否则 0；响应包含：

- `detail.selected_option`
- `detail.correct_option`
- `detail.evidence_boundary`
- `detail.npc_disclosure`
- `ending_id`：`judgement_correct` 或 `judgement_incorrect`

这些服务生成的 ending ids 不等同于 package `endings.yml` 记录。当前雪村的 `endings.yml` 明确是 `endings: []`，因此不要声称它包含完整结局文件；复盘由 submission/review 持久化路径生成。

## 当前权威雪村单人垂直切片

规范内容位于 `script-packages/snow-village`，可由 loader 导入并由 live REST/YAML/LangGraph 路径执行。Mock 只是 UI fixture。

### 包元数据

- id：`snow-village`
- title：`雪落之前：后门的脚印`
- version：`0.1.0`
- description：`卓司元调查王氏杀猪菜后门异常的首个单人垂直切片。`
- genre：`悬疑`、`互动小说`
- difficulty：1
- duration：30 分钟
- max players：1
- entry stage：`return_to_snow_village`

它是 `legacy_single` 范围的单人切片，不是多人 fixture。

### 阶段顺序

1. `return_to_snow_village` / 炉火未熄
   - 场景 `restaurant-hall`。
   - 阅读第一章、与王大达交谈并请求推进。
2. `investigate_back_alley` / 调查后巷
   - 场景 `back-alley`。
   - 调查热点、发现线索/证据、查看截图后推进。
3. `confront_wangdada` / 没有打开的门
   - 解锁并阅读第二章。
   - 向王大达出示后门截图后推进。
4. `back_door_judgement` / 后门判断
   - 展示有限事实判断题并提交 option。

### 当前 IDs 和内容

- 玩家角色：`zhuosiyuan` / 卓司元。
- NPC：`wangdada` / 王大达。
- 场景：`restaurant-hall`、`back-alley`。
- 热点：`back-door-traces` / 后门旁的痕迹，坐标 x=58、y=44。
- 线索：`clue-back-alley-note` / 后巷便签。
- 证据：`evidence-back-door-image` / `21:13 后门截图`。
- 证实边界：21:13 后门半开、门内暖光和不可辨认的影子；不能确认身份、进出方向、开门者、目的或犯罪。

热点的 YAML `on_click` 会发现上述线索和证据，并生成 DM 叙述。前端 `/demo/live` 从 presentation 获取热点坐标，但不会获取这些服务端规则。

### Judgment

问题：`根据当前材料，哪项最符合已证实事实？`

正确 option 是 `C`：

> 王大达关于没人来过的说法不完整；至少可确认后门在21:13半开，但不能确认开门者和目的。

提交请求体是 `{ "option": "C" }` 这一类窄契约。正确得 100、错误得 0；响应 ending id 是 `judgement_correct`/`judgement_incorrect`。当前 `npc_disclosure` 字段为 `null`，具体王大达证词由出示证物的 NPC reaction/chat 路径提供。

### 人物章节

- `zhuosiyuan-chapter-01` / 炉火未熄
  - `release.type: game_start`
  - `stage_min: return_to_snow_village`
- `zhuosiyuan-chapter-02` / 没有打开的门
  - `release.type: rule`
  - `rule_id: first_evidence_set_completed`
  - `stage_min: investigate_back_alley`
  - 在 `confront_wangdada` stage-entry 的 `unlock_character_chapter` 事件中发放。

两章都只授权给选择卓司元的当前 session，状态为 `unlocked`/`viewed`。

### 实际文件范围

当前 package 包含：

- `package.yml`
- 4 个 stage YAML 和 `_index.yml`
- 2 个 character YAML 和 `_index.yml`
- 2 个 character chapter Markdown
- 1 个 clue round YAML
- 1 个 evidence YAML
- 2 个 scene YAML
- `endings.yml`，内容为 `endings: []`
- 3 个 SVG assets：两个场景和一张证物图

当前 package 没有可用的 `media/*.yml` 或 `dm_guide/*.yml` 内容；这些只是 loader 支持的可选扩展，不能描述成雪村已经具备的完整媒体/DM 材料。

## 条件 DSL 和导入期校验

`engine/core/condition_evaluator.py` 已实现组合条件、常量条件，以及阶段、线索/证据、证物出示、人物章节阅读、对话、玩家行为、时间、提交、事件、计数、首玩和提示等叶子。`evaluate_condition()` 使用相关 GameState 片段生成缓存键；trace API 用于调试。

loader 会在导入期校验 condition/event/action 类型和跨文件引用，包括阶段、角色、章节、场景、线索、证据、媒体和结局。运行时仍以最新 checkpoint GameState 为权威，有限 session JSONB 用于查询投影和无 checkpoint 时 bootstrap。

## 变更指引

修改领域行为时，区分：

- 产品/设计规格。
- package loader/schema 和可导入内容。
- migrations/table metadata。
- runtime service/repository/StateGraph 行为。
- presentation 与 chapter 授权 API。
- 前端 live client/boundary。
- 仅用于 UI 预览的 Mock 数据。

当前单人内容以 `script-packages/snow-village` 为准；旧 `supabase/seed/dev_seed.sql` 和旧 Mock 故事不能覆盖该权威包。
