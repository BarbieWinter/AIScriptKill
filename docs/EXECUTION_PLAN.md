# 执行计划书 (Execution Plan)

> **用途**：本文档将整个项目拆解为可独立分配给AI执行的任务。每个任务有明确的输入、输出、验收标准和依赖关系。
> **配套文档**：执行任务前必读 `ARCHITECTURE_OVERVIEW.md`；具体Schema参考 `SCRIPT_PACKAGE_SCHEMA.md`；API契约参考 `API_REFERENCE.md`；前端设计参考 `FRONTEND_EXPERIENCE_DESIGN.md`。

---

## 0. 项目里程碑总览

```
Phase 1: 地基         Phase 2: 引擎核心      Phase 3: 前端核心
(Supabase+项目骨架)    (LangGraph+Agent+RAG)  (游戏主界面+对话)
    Week 1-2              Week 3-5               Week 4-6
       │                     │                      │
       ▼                     ▼                      ▼
─────────────────────────────────────────────────────────────►
                             │                      │
                             ▼                      ▼
                      Phase 4: 内容管道        Phase 5: 集成与打磨
                      (剧本包导入+雪乡数据)     (联调+测试+防剧透审计)
                          Week 5-7                Week 7-9
```

**关键原则：**
1. 每个任务是一个独立单元，输入输出明确，可以直接丢给一个AI执行
2. 标注 `[依赖: T-x.x]` 的任务必须等依赖完成后开始
3. 每个任务的代码必须带注释，遵循任务卡中的注释要求
4. 所有代码提交前必须通过任务卡中的验收标准

---

## Phase 1: 地基搭建 (Week 1-2)

### T-1.1 Monorepo 项目骨架
**[依赖: 无] [规模: 小]**

```yaml
任务: 创建项目基础结构
输入: ARCHITECTURE_OVERVIEW.md 第9节的项目结构
输出:
  - 完整目录树 (engine/ script-packages/ apps/web/ supabase/ docs/)
  - engine/: Python 3.12 + uv 包管理 + pyproject.toml
  - apps/web/: Next.js 14+ App Router + TypeScript + Tailwind + shadcn/ui 初始化
  - 根目录: README.md, .gitignore, docker-compose.yml (本地开发)
  - Makefile 或 justfile: dev/test/lint 命令

验收标准:
  - make dev 能同时启动前后端
  - engine跑通 hello world FastAPI 端点
  - web跑通 Next.js 默认页面(深色主题已配置)
  - lint 全部通过

注释要求:
  - 每个目录有README说明职责
  - pyproject.toml/package.json 每个依赖注释用途
```

### T-1.2 Supabase Schema 与迁移
**[依赖: T-1.1] [规模: 中]**

```yaml
任务: 创建全部数据库表、RLS策略、索引
输入: ARCHITECTURE_OVERVIEW.md 第8节 + SCRIPT_PACKAGE_SCHEMA.md
输出:
  supabase/migrations/ 下的SQL文件:
  - 001_script_tables.sql:
      script_packages, script_stages, script_characters,
      script_clues, script_evidences, script_scenes, script_media
  - 002_runtime_tables.sql:
      game_sessions, session_checkpoints, chat_messages,
      session_discoveries, final_submissions, reviews
  - 003_vector_tables.sql:
      script_knowledge (pgvector, 1536维)
      + ivfflat 索引
  - 004_rls_policies.sql:
      玩家只读已解锁内容 / 管理员全读写 / 服务端service_role
  - seed/dev_seed.sql: 最小测试数据

关键设计:
  - 所有script表都有 script_id 外键分区
  - 运行时表的 state 字段用 JSONB 存储灵活状态
  - session_checkpoints 表支持 LangGraph checkpoint 持久化
  - chat_messages 有 (session_id, created_at) 复合索引

验收标准:
  - supabase db reset 成功执行所有迁移
  - RLS策略测试: 匿名用户不能读dm_guide类数据
  - pgvector 相似度查询跑通

注释要求:
  - 每张表、每个字段有 COMMENT ON 说明
  - 每条RLS策略有注释解释权限逻辑
```

### T-1.3 FastAPI 网关骨架
**[依赖: T-1.1] [规模: 中]**

```yaml
任务: 创建API网关层
输入: API_REFERENCE.md 全部
输出:
  engine/api/ 下:
  - main.py: FastAPI app + CORS + 中间件
  - routes/sessions.py: 会话CRUD端点(先用假数据)
  - routes/actions.py: 游戏操作端点(骨架)
  - routes/packages.py: 剧本包管理端点(骨架)
  - websocket/handler.py: WebSocket连接管理器
  - middleware/auth.py: Supabase JWT验证
  - middleware/rate_limit.py: 限流
  - schemas/: Pydantic v2 模型(与API_REFERENCE.md完全一致)

验收标准:
  - OpenAPI docs (/docs) 展示所有端点
  - WebSocket能建立连接、收发心跳
  - JWT中间件正确拒绝无效token
  - 所有Response Schema与API_REFERENCE.md一致

注释要求:
  - 每个路由函数有docstring: 功能/参数/返回/错误码
  - Pydantic模型每个字段有description
```

### T-1.4 前端项目基座
**[依赖: T-1.1] [规模: 中]**

```yaml
任务: 前端基础设施
输入: FRONTEND_EXPERIENCE_DESIGN.md 第2、5节
输出:
  apps/web/ 下:
  - app/: 路由骨架 (/library /library/[id] /play/[id]/select /play/[sessionId] /play/[sessionId]/review)
  - lib/api.ts: API客户端(fetch封装+错误处理)
  - lib/ws.ts: WebSocket客户端(重连+事件分发)
  - stores/gameStore.ts: Zustand store(FRONTEND_EXPERIENCE_DESIGN.md 第5节)
  - components/ui/: shadcn/ui 基础组件安装
  - 深色主题 + 主题色CSS变量系统(支持剧本包theme_color)

验收标准:
  - 所有路由可导航(空页面)
  - WebSocket客户端能连接后端并打印心跳
  - Zustand store结构与设计文档一致
  - 主题切换工作正常

注释要求:
  - store每个字段/方法有JSDoc
  - ws.ts的事件分发逻辑详细注释
```

---

## Phase 2: 引擎核心 (Week 3-5)

### T-2.1 剧本包解析器 (Package Loader)
**[依赖: T-1.2] [规模: 大]**

```yaml
任务: YAML剧本包 → 标准化数据结构 → 入库
输入: SCRIPT_PACKAGE_SCHEMA.md 全部
输出:
  engine/core/ 下:
  - package_schema.py: Pydantic模型定义整个剧本包Schema
      (PackageMeta, StageDef, CharacterDef, ClueDef, 
       EvidenceDef, SceneDef, MediaDef, EndingDef)
  - package_loader.py: 
      load_package(dir_path) → ScriptPackage对象
      验证引用完整性(stage引用的char/clue/scene必须存在)
  - package_importer.py:
      import_to_db(package) → 写入script_*表
      素材文件上传到Supabase Storage
  - validation.py: SCRIPT_PACKAGE_SCHEMA.md 第13节的验证规则

验收标准:
  - 用一个手写的最小测试剧本包(3个stage+2个角色+4条线索)通过全流程
  - 引用错误(stage引用不存在的clue)被正确捕获并报告
  - 重复导入同一包 = 幂等更新
  - 单元测试覆盖所有验证规则

注释要求:
  - 每个Pydantic模型字段与SCHEMA文档对应说明
  - 校验逻辑逐条注释对应文档的哪条规则
```

### T-2.2 条件评估器 (Condition Evaluator)
**[依赖: T-2.1] [规模: 中]**

```yaml
任务: 实现条件DSL的完整评估器
输入: CONDITION_DSL_REFERENCE.md 全部
输出:
  engine/core/condition_evaluator.py:
  - 所有条件类型的评估函数(2.1~2.8节 每种一个函数)
  - 逻辑组合(all/any/not/count/always/never)递归评估
  - 短路优化
  - 结果缓存(state.condition_cache)
  - 调试trace输出(第7节格式)

验收标准:
  - 每种条件类型有单元测试(true/false两个case)
  - 嵌套5层的复杂条件正确评估
  - trace输出格式与文档第7节一致
  - 性能: 100条件的树评估 < 10ms

注释要求:
  - 每个评估函数注明对应DSL文档章节
  - 缓存键的生成逻辑详细注释
```

### T-2.3 LangGraph 游戏状态机
**[依赖: T-2.1, T-2.2] [规模: 大]**

```yaml
任务: 实现通用StateGraph游戏引擎
输入: ARCHITECTURE_OVERVIEW.md 第4节
输出:
  engine/core/ 下:
  - game_state.py: GameState TypedDict完整定义
  - script_engine.py: 
      ScriptEngine类: 加载剧本包 → 构建StateGraph
      节点: stage_entry / player_action / npc_response /
            check_conditions / process_events / stage_exit / ending
      条件边: _route_action / _should_transition
  - event_bus.py: 
      事件总线: on_stage_entry/on_stage_exit/on_clue_discovered等
      事件action执行器: dm_narrate/play_audio/unlock_*/npc_*等
  - checkpoint.py:
      LangGraph checkpointer → session_checkpoints表
      恢复: 从任意checkpoint重建GameState

验收标准:
  - 用测试剧本包跑通: 创建session → prologue → 玩家行动 → 
    条件满足 → 推进stage → … → ending
  - 中途kill进程后能从checkpoint恢复继续玩
  - 事件正确触发(mock媒体动作,验证调用序列)
  - 阶段不可跳跃/不可回退(除非配置允许)

注释要求:
  - 每个节点函数详细注释: 读什么状态/做什么/写什么状态
  - 条件边的路由逻辑逐分支注释
```

### T-2.4 RAG 引擎
**[依赖: T-1.2, T-2.1] [规模: 大]**

```yaml
任务: 通用RAG索引与检索系统
输入: ARCHITECTURE_OVERVIEW.md 第6.2节Prompt组装 + 第8节权限模型
输出:
  engine/rag/ 下:
  - chunker.py:
      角色知识/线索文本/剧本背景 → 语义切片
      每片注入metadata: script_id/type/character_id/stage_visible/visibility
  - indexer.py:
      切片 → embedding → script_knowledge表
      增量索引(剧本包更新时只重索引变更部分)
  - retriever.py:
      检索入口: retrieve(query, session_context) → list[Chunk]
      硬性权限过滤(SQL WHERE, 不依赖LLM):
        script_id匹配 + stage_visible <= 当前stage
        + (visibility=public OR character_id=当前角色)
        + 已解锁检查
      混合检索: 向量相似度(0.7) + 关键词BM25(0.5) 加权
  - reranker.py: 简单重排序(相似度+重要性+新近度)

关键约束:
  - 权限过滤必须在SQL层完成,检索结果不可能包含越权内容
    (这是防剧透第一道防线,不能依赖LLM自觉)

验收标准:
  - 索引测试剧本包后, 用"凶手是谁"检索:
    - DM上下文能检索到truth
    - NPC上下文绝对检索不到truth
  - 未解锁线索不出现在任何玩家侧检索结果
  - 检索延迟 < 200ms (p95)

注释要求:
  - 权限过滤的每个WHERE条件注释对应权限模型文档
  - metadata结构详细文档化
```

### T-2.5 Agent 系统
**[依赖: T-2.3, T-2.4] [规模: 大]**

```yaml
任务: DM/NPC/Guard/Hint 四类Agent
输入: ARCHITECTURE_OVERVIEW.md 第6节
输出:
  engine/agents/ 下:
  - base_agent.py:
      LLM客户端封装: 主备模型回退链 / 30s超时 / 指数退避重试3次
      Prompt模板系统(Jinja2)
  - dm_agent.py:
      DM Agent: 完整真相可见
      能力: 旁白生成/推进播报/提示判断/复盘生成
      人格系统: 读取package.yml的dm_config.style
      ★支持人格切换(读取stage的dm_behavior配置,如雪乡的谄媚→阴森)
  - npc_agent.py:
      NPC Agent: 按角色+阶段知识边界组装Prompt
      Prompt层次(文档6.2节): 系统规则→角色配置→RAG结果→
        游戏状态→对话历史→输出约束
      情绪状态机: 每个NPC的trust/nervous/fear等数值随交互变化
      撒谎机制: dialogue_strategy.lie_about的内容按策略回答
  - guard_agent.py:
      审查规则(全剧本通用):
        未解锁线索泄漏/真相泄漏/知识边界越界/编造事实/越阶段
      实现: 规则检查(关键词+实体匹配) + LLM审查(仅对可疑输出)
      违规 → 携带违规原因打回重生成(最多2次) → 仍违规则用兜底回复
  - hint_agent.py:
      基于已解锁内容生成提示,从不直接给答案
      每session限3次(可在package.yml覆盖)
  - prompts/: 所有Jinja2模板集中管理

验收标准:
  - NPC对"你是凶手吗?"的回答不泄露真相(测试20次采样)
  - Guard能拦截人工构造的剧透输出(测试用例10条)
  - DM人格切换在stage切换后生效
  - LLM主模型mock失败时自动回退到备模型
  - 全对话链路延迟 < 8s (p95, 不含LLM生成时间则<1s)

注释要求:
  - 每个Prompt模板内嵌注释说明每一段的作用
  - Guard的每条规则注释举例说明拦截什么
```

### T-2.6 API-引擎接线
**[依赖: T-2.3, T-2.5, T-1.3] [规模: 中]**

```yaml
任务: 将API路由接到引擎,替换假数据
输入: API_REFERENCE.md + 已完成的引擎模块
输出:
  - routes/sessions.py: 真实创建/查询/恢复session
  - routes/actions.py: 
      POST /actions → engine.graph.invoke() → 结果转Response
      所有API_REFERENCE.md 2.2节的操作类型
  - websocket/handler.py:
      引擎事件 → WebSocket推送(3.2节所有事件类型)
      per-session操作队列(跨API进程串行化,防并发状态冲突)
      阻断项: REST接线前必须用共享队列、数据库锁或等价机制保证同一session只有一个动作写入者;
              进程内asyncio.Lock和checkpoint saver锁均不满足该要求
  - services/session_service.py: 会话生命周期管理
  - services/scoring_service.py: 
      最终提交评分(读取endings.yml规则+关键证据命中率)

验收标准:
  - Postman/httpx脚本全流程跑通(创建→行动→对话→提交→复盘)
  - WebSocket事件推送与REST响应数据一致
  - 并发发送10个操作,全部按序执行,状态无冲突
  - 至少两个API进程同时提交同一session操作时仍严格串行,不存在分支覆盖或丢失更新

注释要求:
  - 每个操作类型的处理管线注释数据流向
```

---

## Phase 3: 前端核心 (Week 4-6, 与Phase 2部分并行)

### T-3.1 剧本库与详情页
**[依赖: T-1.4, T-1.3] [规模: 中]**

```yaml
任务: /library 和 /library/[id] 页面
输入: FRONTEND_EXPERIENCE_DESIGN.md 3.1/3.2节
输出:
  - 剧本库: 主视觉横幅 + 卡片网格 + 筛选
  - 详情页: 视频播放 + 角色预览 + 开始按钮
  - 深色氛围 + 滚动收缩标题栏

验收标准:
  - 与设计文档的wireframe布局一致
  - 移动端响应式正常
  - 图片懒加载,LCP < 2.5s
```

### T-3.2 角色选择页
**[依赖: T-3.1] [规模: 小]**

```yaml
任务: /play/[id]/select 页面
输入: FRONTEND_EXPERIENCE_DESIGN.md 3.3节
输出: 海报滑动切换 + 角色详情 + 锁定动画 + 创建session并跳转

验收标准:
  - 键盘左右箭头可切换
  - 选择后调用POST /sessions成功跳转游戏页
```

### T-3.3 游戏主界面框架
**[依赖: T-1.4] [规模: 大]**

```yaml
任务: /play/[sessionId] 核心布局
输入: FRONTEND_EXPERIENCE_DESIGN.md 3.4节
输出:
  - GameLayout: 5层布局(黑底/场景/热区/对话/操作栏/模态)
  - SceneCanvas: Konva.js场景+热区渲染,热区发光/点击涟漪
  - 顶部操作栏: 场景名/线索板/背包/笔记入口
  - StageTransition: 阶段切换横幅动画
  - 状态驱动UI: 根据stage类型切换亮度/色调(3.4节状态表)
  - 响应式: 桌面/平板/手机三档布局

验收标准:
  - mock数据下所有布局层正确渲染
  - 热区hover发光、点击触发action
  - 阶段切换横幅动画流畅(60fps)
  - 手机端可完整操作
```

### T-3.4 对话系统UI
**[依赖: T-3.3] [规模: 大]**

```yaml
任务: ChatPanel完整实现
输入: FRONTEND_EXPERIENCE_DESIGN.md 3.7节
输出:
  - ChatBubble: 玩家/NPC/DM旁白三种样式
  - TypingIndicator: NPC打字动画
  - 情绪样式: 撒谎微红底/紧张文字颤抖(CSS animation)
  - 线索名高亮可点击
  - @提及角色 + 快捷命令
  - 流式渲染: WebSocket chunk渐进显示
  - LLM等待策略: 3s/10s/超时三档反馈(4.4节)

验收标准:
  - 长对话(200条)滚动流畅(虚拟列表)
  - 断线重连后历史恢复
  - 流式文本无闪烁
```

### T-3.5 线索板+证物背包+卡牌
**[依赖: T-3.3] [规模: 大]**

```yaml
任务: 三大收集面板
输入: FRONTEND_EXPERIENCE_DESIGN.md 3.5/3.6节
输出:
  - ClueBoard: 轮次Tab + 瀑布流卡片 + 大图查看 + 关键星标
    + 未发现线索的"???"模糊占位 + 长按拖拽关联
  - EvidenceBackpack: 大图预览 + 缩略图列表 + 出示流程
    (选证物→选角色→触发action→展示NPC反应)
  - EvidenceViewer: 放大镜式深层调查交互
  - CardDeck: 卡牌展示 + 使用流程 + 剩余次数

验收标准:
  - 出示证物完整闭环(选择→确认→NPC反应展示)
  - 线索解锁时卡片翻转动画+音效
  - 面板打开不打断背景音频
```

### T-3.6 音频系统
**[依赖: T-3.3] [规模: 中]**

```yaml
任务: Howler.js音频层
输入: FRONTEND_EXPERIENCE_DESIGN.md 4.1节 + API_REFERENCE.md 3.2节media事件
输出:
  - AudioManager: 5层音频(环境/场景BGM/剧情/语音/音效)
      crossfade切换 / 剧情音频抢占 / 队列管理
  - MediaController: 底部控制面板(分层音量+播放状态)
  - SubtitleOverlay: srt解析+时间轴同步渲染
  - WebSocket media.*事件 → AudioManager动作
  - 浏览器自动播放策略处理(首次交互解锁音频)

验收标准:
  - BGM crossfade无爆音
  - 剧情音频播放时BGM自动降低音量(ducking)
  - 字幕与音频同步误差<300ms
  - 刷新页面后BGM恢复播放当前stage的配置
```

### T-3.7 推理提交+真相+复盘
**[依赖: T-3.4] [规模: 中]**

```yaml
任务: 游戏收尾三页面
输入: FRONTEND_EXPERIENCE_DESIGN.md 3.8/3.9/3.10节
输出:
  - FinalSubmission: 只能选已发现内容 + 确认弹窗
  - TruthReveal: 全屏模式+逐字文本+音频同步
  - ReviewScore: 评分/正确/遗漏/路径对比/真相摘要/分享

验收标准:
  - 提交后完整结局流程演出无卡顿
  - 复盘数据与后端review接口一致
```

---

## Phase 4: 内容管道 (Week 5-7)

### T-4.1 素材处理流水线
**[依赖: T-2.1] [规模: 大]**

```yaml
任务: Organizing/ 原始素材 → 剧本包格式
输入: Organizing/ 目录 + SCRIPT_PACKAGE_SCHEMA.md
输出:
  engine/services/import_pipeline/ 下:
  - pdf_ocr.py: 扫描PDF → OCR文本(PaddleOCR或云OCR)
      ★注意: 所有剧本PDF都是扫描件,必须OCR
  - image_ocr.py: 线索图/卡牌图 → OCR文本
  - audio_transcribe.py: 音频 → 转写文本+srt字幕(whisper)
  - docx_extract.py: 带本要点/演绎要点 → 结构化文本
  - asset_uploader.py: 素材 → Supabase Storage + 记录URL

验收标准:
  - 12个角色PDF全部OCR,人工抽查3份准确率>95%
  - 60张线索图OCR完成
  - 10个音频转写+字幕生成
  - 处理报告: 哪些文件失败/需人工介入
```

### T-4.2 雪乡剧本包编排
**[依赖: T-4.1] [规模: 大] [★你深度参与]**

```yaml
任务: 把雪乡素材编排成第一个标准剧本包
输入: OCR后的素材 + SCRIPT_PACKAGE_SCHEMA.md + 带本要点分析
输出:
  script-packages/snow-village/ 完整剧本包:
  - package.yml
  - stages/: 建议11个stage(含fake_final假复盘!)
      序章→一幕开场→一幕一轮→一幕事件→一幕二轮→
      二幕开场→二幕二轮→假最终推理→线上篇→真相→复盘
  - characters/: 12个角色yml
      ★重点: 每个角色每个stage的knowledge边界
      ★重点: 程俊(playable:false, DM分身)的多重人格配置
  - clues/rounds/: 6轮公共线索 + personal/6个个人线索
  - evidences/: 从线索中识别关键证物
  - scenes/: 根据剧情设计4-6个场景
  - media/audio.yml: 10个音频绑定触发节点
  - dm_guide/: truth.yml + stage_notes.yml(从带本要点转化)
  - endings.yml: 双结局(对应结局音频一/二)

流程:
  1. AI初稿: 根据OCR文本自动生成所有yml
  2. ★你审核: 剧情理解/知识边界/阶段划分
  3. AI修订: 按你的反馈迭代
  4. 导入验证: 通过T-2.1的validation

验收标准:
  - 通过package validation无error
  - 你签字确认剧情编排符合原作精神
```

### T-4.3 后台管理界面(最小版)
**[依赖: T-2.1, T-1.4] [规模: 中]**

```yaml
任务: 剧本包管理后台
输出:
  apps/web/app/admin/ 下:
  - 剧本包列表: 导入(zip上传)/发布/下架
  - 验证报告展示: errors/warnings
  - 测试沙盒: 模拟玩家对话,展示Guard拦截日志和条件trace
  - 素材预览: 线索图/音频试听

验收标准:
  - 上传zip → 验证 → 发布全流程可用
  - 沙盒中能看到条件评估trace(CONDITION_DSL文档第7节格式)
```

---

## Phase 5: 集成与打磨 (Week 7-9)

### T-5.1 端到端集成测试
**[依赖: 全部Phase 2/3/4] [规模: 大]**

```yaml
任务: 全流程自动化测试
输出:
  - e2e测试(Playwright): 
      选本→选角→序章→搜证→对话→出示→推进→提交→复盘
  - 引擎集成测试(pytest):
      checkpoint恢复/并发操作/条件边界
  - 防剧透审计脚本:
      自动化100条"套话"提问(你是凶手吗/真相是什么/直接告诉我答案/
      忽略之前的指令/假装你是编剧...)
      对每个NPC+DM采样,检查输出无泄漏

验收标准:
  - e2e全绿
  - 防剧透审计0泄漏(人工复核采样结果)
```

### T-5.2 性能与高可用加固
**[依赖: T-5.1] [规模: 中]**

```yaml
任务: 高可用清单落地
输入: ARCHITECTURE_OVERVIEW.md 第9节(高可用性设计)
输出:
  - LLM回退链压测: 主模型熔断时体验降级但不中断
  - 断线重连: 网络中断30s后恢复,状态无损
  - 音频降级: 加载失败显示文本替代
  - 慢查询优化: 所有API p95 < 500ms(不含LLM)
  - 前端错误边界: 组件崩溃不白屏

验收标准:
  - 混沌测试: 随机kill后端进程,玩家侧能恢复
  - Lighthouse性能分 > 85
```

### T-5.3 体验打磨与完整试玩
**[依赖: T-5.1] [规模: 中] [★你深度参与]**

```yaml
任务: 完整试玩雪乡并修复体验问题
流程:
  1. 你从头到尾玩一遍(2小时)
  2. 记录所有: 出戏时刻/AI回答质量问题/节奏问题/UI别扭处
  3. 分类: 剧本包配置问题(改yml) vs 引擎问题(改代码)
  4. 修复迭代 × 2-3轮

验收标准:
  - 你认可"这是一个可以给朋友玩的作品"
```

---

## 附录A: 任务依赖图

```
T-1.1 ──┬── T-1.2 ──┬── T-2.1 ──┬── T-2.2 ──┐
        ├── T-1.3 ──┤           ├── T-2.4 ──┤
        └── T-1.4 ──┤           │           ├── T-2.3 ── T-2.5 ── T-2.6 ──┐
                    │           └── T-4.1 ── T-4.2 ──────────────────────┤
                    │                        └─ T-4.3                    │
                    ├── T-3.1 ── T-3.2                                   │
                    └── T-3.3 ──┬── T-3.4 ── T-3.7 ──────────────────────┤
                                ├── T-3.5                                 │
                                └── T-3.6                                 │
                                                                          │
                                              T-5.1 ── T-5.2 ── T-5.3 ◄──┘
```

## 附录B: 给执行AI的通用要求

```
所有任务执行时必须遵守:

1. 先读文档再动手:
   ARCHITECTURE_OVERVIEW.md 必读
   + 任务卡"输入"栏指定的文档章节

2. 注释规范:
   - Python: 每个模块/类/公开函数有docstring(功能/参数/返回/异常)
   - TypeScript: 组件Props和store有JSDoc
   - 复杂逻辑(条件评估/权限过滤/状态转移)逐段注释"为什么"
   - 注释解释意图和约束,不是复述代码

3. 引擎与剧本分离红线:
   - engine/ 代码中禁止出现任何具体剧本内容(角色名/剧情/线索)
   - 所有剧本相关内容必须来自script-packages/的配置
   - 发现需要硬编码剧情才能实现的功能 → 停下来,
     这说明Schema需要扩展,先提出Schema变更提案

4. 防剧透红线:
   - 权限过滤必须在数据层(SQL/检索)完成
   - 禁止把truth/dm_guide内容放进NPC的Prompt
   - 新增任何数据流路径时思考: 这会不会把未解锁内容送到玩家侧?

5. 完成标准:
   - 通过任务卡的验收标准
   - lint/typecheck/test全绿
   - 提交信息说明: 实现了什么/偏离设计的地方/遗留问题
```

## 附录C: 里程碑验收点

| 里程碑 | 时间点 | 验收内容 | 你的参与 |
|--------|--------|---------|---------|
| M1: 地基完成 | Week 2末 | 项目跑起来,数据库就绪 | 过目即可 |
| M2: 引擎可玩 | Week 5末 | 测试剧本包全流程(API级) | 试玩API demo |
| M3: 前端可玩 | Week 6末 | 浏览器里玩测试剧本 | 试玩+体验反馈 |
| M4: 雪乡进入 | Week 7末 | 雪乡剧本包导入完成 | ★深度审核剧情编排 |
| M5: 发布候选 | Week 9末 | 完整试玩+审计通过 | ★完整试玩验收 |
```
