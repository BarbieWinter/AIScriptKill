# 剧本与玩法领域

## 产品边界

核心领域是固定剧本的 AI 剧本杀。`/doc/剧本系统设计.md` 是最好的产品来源：系统应该保护高质量谜题的确定性，同时用 AI 提供沉浸感、自然交互、受控阶段推进和复盘。

AI 可以：

- 扮演 DM 和 NPC。
- 在当前阶段和角色知识范围内自然回答。
- 控制流程，并触发线索、证据、场景和媒体。
- 辅助最终复盘和评分。

AI 不应：

- 改变凶手、动机或关键证据。
- 发明主线故事事实。
- 泄露锁定线索、仅 DM 可见材料或未来阶段信息。
- 向玩家暴露后台、销售或 DM 材料。

这个边界解释了为什么仓库强调剧本包、RLS、可见性元数据、剧本包 schema，以及 Guard/RAG 概念。

## 主要领域概念

### 剧本包

剧本包是内容单元。`/docs/SCRIPT_PACKAGE_SCHEMA.md` 描述了预期目录形态，包括 `package.yml`、`stages/`、`characters/`、`clues/`、`evidences/`、`scenes/`、`media/`、`dm_guide/`、`endings.yml` 和 `assets/`。

当前后端导入以 zip 为主，也有 `load_package_directory()` 目录入口。`engine/core/package_loader.py` 预期归档中恰好有一个 `package.yml`，通过 `engine/core/package_yaml.py`、`package_records.py` 和 `package_validation*.py` 解析/校验，并把结构行加载到数据库表。

当前 loader 要求：

- `package.yml` 包含 `metadata.id`、`metadata.title`、`metadata.version` 和 `engine.entry_stage`。
- `stages/` 下至少一个阶段 YAML。
- `characters/` 下至少一个角色 YAML。

当前 loader 可选但支持：

- `characters/_index.yml`，用于可玩性/排序元数据。
- `clues/rounds/*.yml`，用于线索轮次。
- `evidences/*.yml`。
- `scenes/*.yml`。
- `media/*.yml`，带音频/图片资产列表。
- `endings.yml`，用于导入结局、触发条件和 on_trigger 事件。
- `dm_guide/*.yml`，用于导入 DM 私密资料，内容不进入公开 `script_packages.config`。
- `assets/` 下的素材文件；loader 会收集为 `PackageAssetRecord`，可选通过 storage 后端上传并把 YAML 中匹配的本地路径重写为 URL。

### 阶段

阶段是游戏推进单元。设计文档把阶段描述为带进入和退出条件的受控轮次/幕。当前后端把完整阶段定义存入 `script_stages.definition`，并在创建会话时使用其中一个小子集：来自 `engine/repositories/session_seed.py` 的 `available_actions`、`available_characters` 和 `available_scenes`。

如果阶段省略可用动作，当前后端默认使用 `talk_to_npc`、`examine_scene` 和 `open_clue_board`。如果省略场景，当前场景默认是 `start`。Loader 还支持 `/docs/SCRIPT_PACKAGE_SCHEMA.md` 中的 action object 写法，会把 `available_actions[].id` 归一化为运行期字符串列表，并把 label/description 保存在 `action_definitions`。

### 角色

角色可以是可玩角色、NPC 或 DM alter ego。当前剧本包加载会读取角色文件和可选 `_index.yml` 元数据到 `script_characters`，包含 `is_playable`、`is_dm_alter_ego` 和 `sort_order`。

产品设计要求角色知识边界：NPC 只能知道其角色和当前阶段允许知道的内容。这尚未完整实现；当前动作回复是固定占位内容。

### 线索和证据

源码和 schema 中，线索与证据是分开的概念：

- 线索是调查事实，存储在 `script_clues`，通过 `session_discoveries` 中的 `entity_type='clue'` 解锁。
- 证据是道具、关键证据、技能卡或普通证据，存储在 `script_evidences`，发现后同样在 discoveries 中跟踪。

RLS 和查询代码使用阶段可见性、角色可见性等元数据来防剧透。当前后端动作逻辑只会在 `examine_scene` 时解锁固定的 `broken_glass` 线索。

### 场景和媒体

按预期设计，场景是带背景/热点的互动地点。当前后端存储场景定义和背景 URL，但真实后端尚未从剧本包内容求值热点。前端 Mock 玩法中最完整的场景/热点实现位于 `apps/web/lib/mock-data.ts` 和 `components/game/SceneHotspots.tsx`。

媒体资产定义存储在 `script_media`，类型包括 `bgm`、`story`、`sfx`、`voice`、`image` 和 `video`。剧本包中的二进制素材来自 `assets/`，导入准备阶段可通过 `package_storage.py` 上传到 Supabase Storage，并把 package config、线索图片、证据图片、场景背景、媒体文件、结局和 DM guide 中的本地路径改写为 URL。`engine/media/orchestrator.py` 仍是占位模块。

### DM 指引、真相和复盘

设计文档把 DM 材料和真相数据视为特权内容。当前后端剧本包 loader 会导入 `endings.yml` 为 `EndingRecord`，校验 ending condition 和 on_trigger 中的引用，并通过 `PackageImportRepository` 写入 `script_endings`。`dm_guide/` 会保留在 `ScriptPackageImport.dm_guide`，导入时写入仅 service-role 可访问的 `script_dm_guides`，不会进入公开可读的 `script_packages.config`。评分/复盘逻辑在 `engine/services/action_mappers.py` 和 `engine/repositories/session_mutations.py` 中仍是占位级别。

## 雪村状态

仓库包含雪村资产和设计引用：

- `/doc/剧本系统设计.md` 描述 `Organizing/` 包含剧本 PDF、线索、音频、海报、道具、DM 材料和运营资产。
- `apps/web/lib/mock-data.ts` 包含可执行的 Mock 雪村玩法数据。
- `/script-packages/snow-village` 包含预期剧本包目录，但在已检查的树中没有 package YAML 文件。

不要假设雪村已经转换成可导入的后端剧本包。如果要转换，应以 `/docs/SCRIPT_PACKAGE_SCHEMA.md` 和 `engine/core/package_loader.py` 作为绑定契约，并在把 Mock 数据视为规范前先调和其中的不一致。

## 条件 DSL 和导入期校验

`/docs/CONDITION_DSL_REFERENCE.md` 定义了预期 YAML DSL，用于阶段推进、线索/证据检查、对话检查、玩家动作和布尔组合。当前 `engine/core/condition_evaluator.py` 已实现核心 DSL 评估、组合递归、短路、缓存和 trace 输出；`engine/core/script_engine.py` 已在 core StateGraph 中用它评估阶段退出和结局分支。REST action endpoint 仍走 `engine/services/action_mappers.py` 的确定性占位流程，后续还需要把 API 层切到 core 引擎。

当前 evaluator 支持组合条件 `all`、`any`、`not`、`count`，常量条件 `always`、`never`，以及这些叶子类别：阶段/幕进度、线索发现计数、单线索/证据发现、证据出示给 NPC、角色对话次数、已触发对话、玩家关键词、NPC 状态阈值、玩家动作/请求/卡牌、阶段内时间和真实时间、最终提交正确/错误、关键证据使用、推理链完成、事件已触发/未触发、session counter、首次游玩和提示次数。`evaluate_condition()` 使用 `GameState` 相关片段生成缓存键；`evaluate_condition_with_trace()` 和 `format_condition_trace()` 用于调试；`ConditionEvaluationOptions.force_conditions` 可在测试/沙盒中覆盖某类条件结果。

不过 loader 已经会做导入期校验：`package_validation_context.py` 列出支持的 condition type、event action 和 gameplay action；`package_reference_validation.py` 校验阶段、角色、场景、线索轮次、线索、证据、媒体和结局引用；`package_event_validation.py` 校验 `play_audio`、`unlock_scenes`、`unlock_clue_round`、`npc_enter_scene`、`npc_emotion`、`clue_discover`、`transition_to` 等事件；`package_asset_validation.py` 校验本地素材路径存在，并把角色缺少阶段知识作为 warning 返回。

## 变更指引

修改领域行为时，先判断你改的是：

- `docs/` 或 `doc/` 中的产品/设计规格。
- `engine/core/package_schema.py` 和 `package_loader.py` 中的可导入剧本包契约。
- `supabase/migrations/` 和 `engine/db/tables.py` 中的数据库表示。
- services/repositories 中的运行期行为。
- `apps/web/lib/mock-data.ts` 中的前端 Mock 体验。

保持这些层彼此对齐。目标文档、Mock 玩法、空剧本包目录和后端占位行为之间已经存在不一致。
