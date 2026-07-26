# AI 沉浸式悬疑互动剧 — 系统架构总览（历史设计）

> [!IMPORTANT]
> 本文是项目最初**单人多 NPC 智能体方向**的架构设计。该玩法方向已移出当前产品
> （见 [`PRODUCT_DIRECTION_AND_IMPLEMENTATION_STATUS.md`](PRODUCT_DIRECTION_AND_IMPLEMENTATION_STATUS.md)）。
> 仍然有效的部分：引擎与剧本包分离原则（第 1 节）、剧本包加载流程（第 5 节）、
> 数据权限模型（第 8 节）、高可用与设计决策（第 9、11 节）。
> 已过期的部分：NPC Agent 对话玩法（第 4、6 节）、以搜证为主的交互假设。
> 当前实现结构见 [`../openwiki/architecture/system.md`](../openwiki/architecture/system.md)。

> 版本 v1.0 | 配套文档：`SCRIPT_PACKAGE_SCHEMA.md` `CONDITION_DSL_REFERENCE.md` `API_REFERENCE.md` `FRONTEND_EXPERIENCE_DESIGN.md` `EXECUTION_PLAN.md`

---

## 1. 核心架构哲学

**引擎 ≠ 剧本**

```
┌────────────────────────────────────────────────────────────┐
│  Script Engine (一次编写，永不修改)                         │
│  通用状态机 · Agent工厂 · RAG引擎 · 媒体编排器 · 评分系统   │
└────────────────────────┬───────────────────────────────────┘
                         │ 加载
┌────────────────────────▼───────────────────────────────────┐
│  Script Package (可插拔数据 — 你编排的内容)                  │
│  stages/ · characters/ · clues/ · scenes/ · media/ · dm_guide/
└────────────────────────┬───────────────────────────────────┘
                         │
              ┌──────────┼──────────┐
              ▼          ▼          ▼
        ┌──────────┐ ┌──────┐ ┌──────────┐
        │ 雪乡剧本  │ │ 新本 │ │ 后续剧本 │
        └──────────┘ └──────┘ └──────────┘
```

**核心原则：**
- 所有游戏逻辑编码在引擎中，所有游戏内容编码在剧本包中
- 引擎不知道具体剧情，只执行通用节点：stage_entry → player_action → check_conditions → stage_exit
- 剧本包不知道引擎实现，只配置：进入条件、退出条件、事件列表、角色知识
- **你调优剧本 = 改yml，不写代码**

---

## 2. 整体技术栈

```
Layer          Technology
────────────────────────────────────────────────────────────
Frontend       Next.js 14+ (App Router) · shadcn/ui · Tailwind
               Zustand (状态管理) · TanStack Query (数据获取)
               Howler.js (音频) · Konva.js (场景热区交互)
               TipTap (笔记编辑器) · WebSocket (实时推送)

API Gateway    FastAPI · Pydantic v2 · WebSocket

Engine         LangGraph (StateGraph) · LangChain · Python 3.12+

RAG            pgvector · sentence-transformers ·
               ‍混合检索 (向量 + BM25) · 权限过滤

Media          TTS (Edge-TTS / OpenAI TTS) · FFmpeg ·
               音频时间轴同步

Database       Supabase · Postgres 15 · RLS · Realtime

Storage        Supabase Storage · 分权限bucket

Auth           Supabase Auth · 匿名模式 + 可选注册

Deploy         Docker · Vercel (前端) · Railway (后端) ·
               Supabase (DB)
```

---

## 3. 系统模块依赖图

```
┌───────────────┐     ┌──────────────────┐     ┌───────────────┐
│   Next.js     │◄───►│   FastAPI API    │◄───►│  LangGraph    │
│   Frontend    │ HTTP│   Gateway        │  WS │  Engine       │
│               │  WS │                  │     │  (核心状态机)   │
└───────┬───────┘     └────────┬─────────┘     └───────┬───────┘
        │                      │                       │
        │                      │                       │
        ▼                      ▼                       ▼
┌───────────────┐     ┌──────────────────┐     ┌───────────────┐
│   Audio/Video │     │   RAG Engine     │     │  Agent        │
│   Player      │     │   (检索+过滤)     │     │  Registry     │
│   (Howler)    │     │                  │     │  (DM/NPC/Guard)│
└───────┬───────┘     └────────┬─────────┘     └───────┬───────┘
        │                      │                       │
        └──────────┬───────────┼───────────────────────┘
                   │           │
                   ▼           ▼
        ┌─────────────────────────────────────┐
        │           Supabase                  │
        │  Auth · Postgres · pgvector ·       │
        │  Realtime · Storage · RLS           │
        └─────────────────────────────────────┘
```

---

## 4. 引擎核心：LangGraph StateGraph

### 4.1 通用状态定义

```python
class GameState(TypedDict):
    """全局游戏状态（所有剧本共享）"""
    # 会话信息
    session_id: str
    script_id: str
    player_id: str
    
    # 流程控制
    current_stage: str           # "prologue" / "act1_round1" / ...
    previous_stage: str | None
    stage_entered_at: str        # timestamp
    
    # 角色信息
    player_character_id: str     # 玩家选择的角色
    npc_agents: dict[str, dict]  # {char_id: {current_mood, trust_level, ...}}
    
    # 解谜状态
    unlocked_clues: list[str]       # 已解锁的线索ID列表
    discovered_evidences: list[str]  # 已发现的证物ID
    completed_events: list[str]      # 已完成的事件ID
    
    # 对话上下文
    chat_history: list[Message]
    pending_npc_responses: list      # 待生成的角色回复
    
    # 条件缓存
    condition_cache: dict[str, bool]
    
    # 事件队列
    pending_events: list[GameEvent]  # 待触发的脚本事件
    
    # 结局状态
    ending_triggered: bool
    ending_id: str | None
    final_submission: dict | None
```

### 4.2 固定节点图

```
                    ┌──────────────┐
                    │    START     │
                    └──────┬───────┘
                           │
                    ┌──────▼───────┐
                    │  stage_entry │  ← 加载当前stage配置，触发on_enter事件
                    └──────┬───────┘
                           │
                    ┌──────▼───────┐
         ┌─────────►│ player_action│  ← 路由到具体行动处理器
         │          └──┬───┬───┬───┘
         │             │   │   │
         │    ┌────────┘   │   └────────┐
         │    ▼            ▼            ▼
         │ ┌────────┐ ┌────────┐ ┌──────────┐
         │ │talk to │ │examine │ │  submit  │
         │ │ NPC    │ │scene/  │ │  final   │
         │ │        │ │evidence│ │          │
         │ └───┬────┘ └───┬────┘ └────┬─────┘
         │     │          │           │
         │     ▼          │           ▼
         │ ┌────────┐     │      ┌──────────┐
         │ │npc_    │     │      │  ending  │──► END
         │ │response│     │      └──────────┘
         │ └───┬────┘     │
         │     │          │
         │     ▼          ▼
         │ ┌──────────────────┐
         │ │  check_conditions│  ← 评估exit_conditions
         │ └──┬───────────────┘
         │    │
         │    ├── stay ────────────────────┘
         │    │
         │    ├── next_stage
         │    │    │
         │    │    ▼
         │    │ ┌────────────┐
         │    │ │ stage_exit │  ← 触发on_exit事件
         │    │ └─────┬──────┘
         │    │       │
         │    └───────┼─────► stage_entry (下一阶段)
         │            │
         └────────────┘
              trigger_event
                   │
                   ▼
              ┌────────────┐
              │fire_events │  ← 播放音频/解锁线索/改变角色状态
              └─────┬──────┘
                    │
                    ▼
               stage_exit
```

### 4.3 图是模板，由剧本包实例化

```python
# 引擎启动时
engine = ScriptEngine.load_package("snow-village")
# engine.graph 是上面模板图的实例
# 每个stage_def的配置决定了：
#   - player_action有哪些分支
#   - check_conditions有哪些条件
#   - stage_entry触发哪些事件
#   - stage_exit触发哪些事件
```

---

## 5. 剧本包加载流程

```
                      ┌─────────────────────┐
                      │   script-packages/   │
                      │   snow-village/      │
                      │     package.yml      │
                      │     stages/          │
                      │     characters/      │
                      │     ...              │
                      └──────────┬──────────┘
                                 │  import_service.py
                                 ▼
┌──────────────────────────────────────────────────┐
│                  Import Pipeline                  │
│                                                   │
│  1. 验证 package.yml Schema 完整性                │
│  2. 解析 stages/_index.yml → 建立阶段顺序        │
│  3. 解析每个 stage YAML → 存入 script_stages    │
│  4. 解析 characters/ → 存入 script_characters   │
│  5. 解析 clues/ → OCR线索图 + 存入 script_clues │
│  6. 解析 evidences/ → 存入 script_evidences     │
│  7. 解析 scenes/ → 存入 script_scenes           │
│  8. 解析 media/audio.yml → 关联各阶段           │
│  9. 生成 embeddings → pgvector索引              │
│ 10. 状态设为 draft / published                   │
└──────────────────────────────────────────────────┘
                                 │
                                 ▼
                      ┌─────────────────────┐
                      │   Supabase 就绪      │
                      │   script_packages    │
                      │   script_stages      │
                      │   script_characters  │
                      │   + pgvector索引     │
                      └─────────────────────┘
```

---

## 6. Agent系统架构

### 6.1 Agent类型

```
┌──────────────────────────────────────────────────────────┐
│                    Agent Registry                         │
│                                                          │
│  根据剧本包配置，运行时实例化                              │
│                                                          │
│  DM Agent (单例)                                          │
│  ├─ 角色：游戏主持人，知道完整真相                         │
│  ├─ Prompt源：dm_guide/truth.yml + 当前stage + 状态       │
│  ├─ 能力：旁白、推进、复盘、假真相/真真相切换              │
│  └─ 人格覆盖：package.yml中定义DM风格（温和/阴森/戏谑）    │
│                                                          │
│  NPC Agent[N] (每个角色一个实例)                           │
│  ├─ 角色：剧情中的嫌疑人/NPC                              │
│  ├─ Prompt源：characters/{id}.yml 知识边界                │
│  ├─ 约束：按stage过滤知道/不知道的信息                     │
│  └─ 状态：情绪值、信任度、撒谎状态（在state.npc_states中）  │
│                                                          │
│  Guard Agent (单例)                                       │
│  ├─ 角色：审查所有AI输出                                  │
│  ├─ 规则：不剧透、不编造、不越权                          │
│  ├─ 内置规则：对所有剧本通用                               │
│  └─ 剧本扩展规则：在dm_guide/中配置额外限制                │
│                                                          │
│  Hint Agent (单例)                                        │
│  ├─ 角色：玩家卡住时给轻量提示                            │
│  ├─ 约束：只引用已解锁线索，不给直接答案                  │
│  └─ 频率控制：每个session限制提示次数                      │
└──────────────────────────────────────────────────────────┘
```

### 6.2 Agent调用流程

```
玩家输入
   │
   ▼
┌─────────────────────────────────────────────────────┐
│ 1. 意图路由（引擎内置，不依赖LLM）                    │
│    ├─ @角色名 → NPC Agent                           │
│    ├─ /dm → DM Agent                                │
│    ├─ /examine [证物] → Evidence Service            │
│    ├─ /card [卡牌] → Prop Service                   │
│    └─ 自然语言 → DM Agent (作为旁白/推进判断)        │
├─────────────────────────────────────────────────────┤
│ 2. Prompt组装                                        │
│    ├─ 系统模板（通用规则）                             │
│    ├─ 角色配置文件（性格/知识边界）                    │
│    ├─ RAG检索结果（权限过滤后）                        │
│    ├─ 当前游戏状态（stage/已解锁/已发生事件）           │
│    ├─ 对话历史（最近N轮）                             │
│    └─ 输出约束（格式/长度/禁止内容）                   │
├─────────────────────────────────────────────────────┤
│ 3. LLM调用                                           │
│    ├─ 主模型：Fable 5 / Opus 4.8                    │
│    ├─ 超时：30s                                      │
│    └─ 重试：指数退避 × 3                             │
├─────────────────────────────────────────────────────┤
│ 4. Guard Agent 审查                                   │
│    ├─ 是否提前透露真相                                │
│    ├─ 是否提到未解锁线索                              │
│    ├─ 是否偏离角色知识边界                            │
│    ├─ 是否编造剧本不存在的事实                         │
│    └─ 违规 → 打回重生成（最多2次）                    │
├─────────────────────────────────────────────────────┤
│ 5. 后处理                                            │
│    ├─ 写入 chat_history                              │
│    ├─ 检查是否触发新事件（出示证物/特定关键词）        │
│    └─ 返回给前端                                     │
└─────────────────────────────────────────────────────┘
```

---

## 7. 多媒体系统架构

```
┌─────────────────────────────────────────────────────────┐
│                 Media Orchestrator                       │
│                                                         │
│  ┌─────────────┐  ┌─────────────┐  ┌───────────────┐   │
│  │ Audio Queue  │  │ Image/Video │  │  Subtitle     │   │
│  │ 播放队列     │  │ 展示控制器   │  │ 同步器        │   │
│  │ 优先级管理   │  │ 轮播/缩放   │  │ 文本+时间轴   │   │
│  │ 交叉淡入淡出 │  │ 过渡动画   │  │ 自动滚动      │   │
│  └──────┬──────┘  └──────┬──────┘  └───────┬───────┘   │
│         │                │                  │           │
│         └────────────────┼──────────────────┘           │
│                          │                              │
│                   ┌──────▼──────┐                       │
│                   │  触发器     │                       │
│                   │  事件→媒体  │                       │
│                   │  映射引擎   │                       │
│                   └────────────┘                       │
└─────────────────────────────────────────────────────────┘

触发器来源：
   stage_entry → 场景BGM + DM旁白音频
   event_fired → 剧情音频（广播/童谣/撞车）
   clue_discovered → 发现音效
   evidence_shown → 证物放大图
   character_emotion → 角色语音（TTS）
   stage_exit → 过渡音效
   ending → 结局音频 + 真相展示
```

---

## 8. 数据权限模型

```
浏览器 / 玩家
      │ 仅调用 /api/v1
      ▼
┌────────────────────────────┐
│ FastAPI 授权、会话归属检查 │
│ 阶段/角色可见性与字段投影  │
└─────────────┬──────────────┘
              │ 服务端数据库角色
              ▼
┌────────────────────────────┐
│ Supabase/Postgres + RLS    │
│ anon/authenticated 无表权限│
└────────────────────────────┘

玩家可见:
  ├─ 当前stage前的所有公开线索（按stage_visible过滤）
  ├─ 分配给该角色的个人线索
  ├─ 已发现的证物详情
  ├─ 当前stage允许对话的角色
  └─ 当前stage开放的场景

玩家不可见:
  ├─ 未到stage的线索/场景
  ├─ 其他角色的个人线索
  ├─ 完整真相 (dm_guide/)
  ├─ DM带本要点
  └─ 其他玩家的游戏状态（多人模式）

管理员可见:
  ├─ 所有剧本包数据
  ├─ 所有游戏会话状态
  ├─ 售后资料
  └─ 玩家行为分析

私有素材:
  ├─ Storage bucket 强制 private
  ├─ 数据库只保存 storage:// 定位符
  └─ T-2.6 在会话鉴权后提供短期签名 URL 或代理下载
```

---

## 9. 高可用性设计

```
风险                   应对策略
──────────────────────────────────────────────────────
LLM API失败           多模型回退链：主→备→缓存→优雅降级
LLM超时               30s超时 + 指数退避(3次)
LangGraph崩溃         Checkpoint持久化：每步写入Supabase
网络中断              前端支持离线重连 + 状态恢复
多媒体加载失败        降级显示/播放：图片→占位图，音频→跳过
RAG无结果             兜底回复：角色"不知道"+ DM"继续调查"
并发请求              per-Session串行化队列
状态不一致            Version stamp乐观锁
```

---

## 10. 数据流全景

```
┌──────────┐   HTTP   ┌──────────┐   Internal   ┌─────────────┐
│  Next.js │◄────────►│ FastAPI  │◄────────────►│ LangGraph   │
│  Frontend│   WebSkt │  Gateway │              │ Engine      │
└─────┬────┘          └────┬─────┘              └──────┬──────┘
      │                    │                           │
      │  WebSocket:        │  REST:                    │  LangGraph:
      │  /ws/{session_id}  │  /api/v1/sessions         │  每步checkpoint
      │                    │  /api/v1/stages            │  → Supabase
      │  Events:           │  /api/v1/characters        │
      │  - chat.message    │  /api/v1/clues             │
      │  - media.play      │  /api/v1/evidences         │
      │  - stage.change    │  /api/v1/media             │
      │  - event.trigger   │  /api/v1/submissions       │
      │                    │  /api/v1/packages          │
      │                    │                           │
      └─────────┬─────────┴───────────────────────────┘
                │
                ▼
         ┌──────────────┐
         │  Supabase    │
         │  Realtime    │
         │  (状态推送)   │
         └──────────────┘
```

---

## 11. 关键设计决策记录

| 决策 | 选择 | 理由 |
|------|------|------|
| 状态管理 | LangGraph StateGraph 而非手写状态机 | LangGraph自带Checkpoint/分支回退/Human-in-loop，适合复杂游戏流程 |
| 剧本包格式 | YAML 而非 JSON | YAML支持注释，更适合人类编排 |
| Agent通信 | 引擎内部函数调用 而非 微服务网络调用 | 减少延迟，LangGraph在同一进程内编排 |
| 前端状态 | Zustand 而非 Redux | 轻量、TypeScript友好、适合游戏类状态 |
| 实时通信 | WebSocket 而非 SSE | 双向通信，支持玩家操作+服务端推送 |
| 用户认证 | 匿名模式优先 | 降低开玩门槛，后续可升级为注册用户 |
| 多媒体存储 | Supabase Storage 而非 CDN | 与数据库同厂商，RLS统一管理 |
| 模型回退 | 预设回退链 而非 动态路由 | 确定性高，避免路由决策本身失败 |
