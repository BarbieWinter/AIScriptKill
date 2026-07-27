# AIScriptKill 产品方向与实现状态总览

> 文档级别：项目级产品与实现边界权威文档  
> 审计日期：2026-07-27
> 实现基线：`af79a9e` 依赖闭合的双人多人候选；场景重构与文档状态同步至本次提交
> 仓库状态：T01 候选闭包已提交，本文不再以临时工作区文件计数判断能力状态
> 适用范围：产品定义、运行权归属、当前完成度、旧方向清理与后续建设顺序

本文档回答四个问题：项目现在实际走到了哪里，最终要做成什么，哪些旧方向已经偏离，以及下一步应该保留、删除、暂停或建设什么。

发生冲突时，产品边界与路线判断以本文档为准；细分实现知识可以继续写入 `openwiki/`。现有 `README.md`、`ARCHITECTURE_OVERVIEW.md`、`SCRIPT_PACKAGE_SCHEMA.md` 和 `MULTIPLAYER_ARCHITECTURE_PLAN.md` 中与本文档冲突的旧描述，应视为待清理资料，而不是当前产品承诺。

---

## 1. 一页结论

```text
┌──────────────────────────────────────────────────────────────────────┐
│ AIScriptKill 当前状态                                                │
├──────────────────────────────────────────────────────────────────────┤
│ 产品方向     多人共享房间 + 私有角色剧本 + 公开讨论 + 受控 AI DM     │
│ 当前可玩性   已提交的双人候选垂直切片可从建房完整通关到复盘           │
│ 当前传输     认证 HTTP 命令 + 2 秒快照轮询；不是实时 WebSocket 游戏流 │
│ 当前流程     固定 READ → DISCUSS → SETTLE → REVEAL，而非通用活动序列 │
│ 当前舞台     可移动且可看到同伴；公开材料仍被热点入口锁住             │
│ 当前 AI DM   未实现；只有真相资料和确定性协作提示                     │
│ 当前风险     契约仍接受部分运行时无法闭合的合法 YAML                  │
└──────────────────────────────────────────────────────────────────────┘
```

最重要的校准是：**项目已经不再停留在“只有大厅”阶段。** `af79a9e` 已提交游戏命令服务、活跃游戏界面、私有章节投影、公共讨论、确定性发放、阶段判断、终局、复盘、持久命令、outbox 基础设施和位置同步；真实双身份浏览器验收已经完整通关。

但这也不等于“多人产品已经完成”。当前实现是一个严格双人、固定流程、HTTP 轮询驱动的候选垂直切片。通用活动模型、受控 AI DM、认证实时事件流、完整断线重连验收，以及旧地图搜证依赖清理仍未完成。当前角色章、讨论、判断和复盘已有固定 UI 入口，但公开材料仍只有空间热点入口，整个多人壳层也仍耦合 legacy hotspot 抽象，和目标边界冲突。

---

## 2. 完成度判定标准

本文只使用以下状态，不用“差不多”“基本完成”或仅凭文件存在来判断：

| 状态 | 判定标准 |
|---|---|
| **已完成** | 前后端闭环可运行，相关测试通过，用户可以实际操作 |
| **部分完成** | 核心代码存在，但集成、测试、适用范围或 UX 仍不完整 |
| **已实现，等待验证** | 代码链路已写出，但缺少足够的真实环境或用户路径验证 |
| **仅设计** | 有契约、类型、文档或方案，没有可运行闭环 |
| **未开始** | 没有形成实质实现 |
| **暂停或移出当前方向** | 不属于当前产品目标；已有代码也不能算当前进度 |

还必须区分能力所在层级：

- **历史基线**：`f9c8a4e` 中已经存在的多人大厅与后端基础。
- **依赖闭合候选**：`af79a9e` 已提交并通过真实栈验证的严格双人垂直切片，可供后续任务增量建设，但不等同于通用多人产品完成。
- **目标能力**：本文确定的方向，可能尚未实现。

T01 已将核心模块、数据库 migration、前后端接线与测试作为一个依赖闭合变更集提交。后续能力判断以 clean checkout 可构建、可迁移、可测试和可实际操作为准，不再引用临时工作区文件计数。

---

## 3. 最终产品定义

AIScriptKill 是一个**多人在线剧本游戏执行平台**。玩家进入同一房间，每人获得私有角色剧本和个人叙事目标，通过公开讨论、信息不对称与观点碰撞推进故事；程序负责可靠执行，受控 AI DM 只在剧本声明的节点提供主持支持。

它的核心不是“在地图上找东西”，也不是“多个 AI NPC 自主扮演一个世界”。第一阶段产品应让一组真人玩家能够稳定完成以下体验：

```text
START
  │
  ▼
创建 / 加入共享房间
  │
  ▼
选择或分配角色 ──► 每人只看到自己的角色剧本与个人目标
  │
  ▼
私有阅读
  │ 全员完成后由程序通过确定性门槛
  ▼
公开讨论与信息交换
  │
  ├── 可选：YAML 声明的 DM checkpoint
  │          AI 只能澄清、提醒、递进提示或建议继续讨论
  │
  ▼
确定性发放下一批公开材料 / 私有章节
  │
  ├── 可选：表演、个人任务、特殊机制
  ├── 可选：一次或多次决策 / 投票
  ▼
结局与真相揭晓
  │
  ▼
复盘
  │
  ▼
END
```

### 3.1 第一版必须成立的产品特征

- 真人多人优先，而不是单人 NPC 多智能体优先。
- 角色信息、角色章节和个人叙事目标默认私有。
- 一般阶段材料默认公开，并由 YAML 在确定节点发放。
- 玩家通过讨论推进理解，不通过地图位置“发现”关键内容。
- 剧本默认是线性的 `START → END`。
- 投票只是可选决策机制，不是每个阶段的固定结构。
- AI DM 是主持支持，不是玩家、裁判或真相决定者。
- 程序必须保证权限、状态、幂等、持久化、同步和恢复。

### 3.2 当前明确不做的产品

- 不做以“一名 AI 对应一个 NPC”为核心的单人玩法。
- 不做依赖场景坐标、热点或可见文档的搜证游戏。
- 不让 LLM 从聊天语义中判断玩家是否“发现线索”。
- 不让 LLM 决定内容是否发放、阶段是否推进或投票结果。
- 不把每阶段投票、多轮投票、平票规则当作平台统一规则。
- 不在第一版自动判断个人叙事目标是否完成。
- 不在第一版承诺任意分支图、复杂机制或开放世界模拟。

---

## 4. 四类权威必须分开

```text
                         ┌─────────────────────┐
                         │ 玩家：结论与选择权   │
                         │ 讨论、判断、表态     │
                         └──────────┬──────────┘
                                    │ 命令
                                    ▼
┌─────────────────────┐   ┌─────────────────────┐   ┌─────────────────────┐
│ YAML：剧本创作权     │──►│ 程序：执行与状态权   │◄──│ AI DM：受限主持权    │
│ 阶段、活动、内容、   │   │ 权限、状态机、持久化 │   │ 澄清、提醒、递进提示 │
│ checkpoint、结局     │   │ 同步、恢复、审计     │   │ 不得直接改状态       │
└─────────────────────┘   └─────────────────────┘   └─────────────────────┘
```

### 4.1 YAML 拥有什么权威

YAML 是创作内容的权威来源，负责：

- 有序阶段与有序活动。
- 每个角色在各阶段获得的私有章节。
- 在确定节点发放的公共材料。
- 可选决策、表演、特殊机制和结局内容。
- AI DM 的私有主持资料、允许出现的 checkpoint 与递进提示。
- 默认线性路径和显式终局。

YAML 不负责：

- 网络断开、重连、连接超时和传输重试。
- 数据库事务、幂等键、版本冲突和 outbox 投递。
- 因玩家跑题而擅自终止游戏。
- 用自然语言条件绕过程序权限。

### 4.2 程序拥有什么权威

程序是运行时真相，负责：

- 谁可以加入、选择角色、准备、开始和发命令。
- 当前房间、阶段、活动、版本号与完成状态。
- 私有信息隔离和参与者安全投影。
- 全员门槛、判断提交、结果计算和结局映射。
- 命令幂等、持久化、事件顺序、恢复和审计。
- 断线期间保持状态不被网络层擅自推进。
- 验证 AI DM 输出不越权。

### 4.3 AI DM 拥有什么权威

AI DM 只拥有受限的主持表达权：

- 解释当前规则和当前可用事实。
- 根据私有主持稿提醒被忽略的问题。
- 按 YAML 预写的层级提供递进提示。
- 在 checkpoint 建议继续讨论或进入程序允许的下一活动。
- 在终局后协助复盘表达。

AI DM 不能：

- 每条聊天都回复或主动打断自由讨论。
- 发明线索、修改角色剧本或提前泄露答案。
- 判断玩家已经“搜到”某条线索。
- 发放内容、修改状态、推进阶段或改变投票。
- 指认嫌疑人、替玩家下结论或操纵选项。
- 在正式决策开始后继续提供结论性引导；此时只能解释程序。

### 4.4 玩家拥有什么权威

玩家拥有讨论、结论和选择权。程序可以验证命令是否合法，DM 可以帮助理解，但系统不能替玩家形成判断。

---

## 5. 目标 YAML：从固定四相迁移到活动序列

当前 `StagePhase` 仍硬编码为 `READ / DISCUSS / SETTLE / REVEAL`，见 `engine/contracts/multiplayer_v1/vocabulary.py:15`。这个模型适合当前双人样例，却把“投票或结算”误放成了每阶段骨架。

目标模型应以有序 `activities[]` 为中心：

```yaml
stages:
  - id: chapter-one
    activities:
      - type: deliver_content
      - type: private_reading
      - type: public_discussion
      - type: dm_checkpoint

  - id: chapter-two
    activities:
      - type: deliver_content
      - type: private_reading
      - type: public_discussion
      - type: dm_checkpoint
      - type: decision

  - id: ending
    activities:
      - type: resolution
      - type: debrief
```

第一批通用活动类型建议为：

| 活动 | 含义 | 是否基础必需 |
|---|---|---|
| `deliver_content` | 按作者配置确定性发放公开或私有内容 | 是 |
| `private_reading` | 玩家阅读自己的角色章节 | 是 |
| `public_discussion` | 真人玩家公开交换信息 | 是 |
| `dm_checkpoint` | 在明确节点请求受控主持支持 | 可选 |
| `personal_task` | 作者声明的个人活动；默认仍是叙事文本 | 可选 |
| `decision` | 共享选择、秘密提交、投票等 | 可选 |
| `performance` | 演绎、小剧场或特殊互动 | 可选 |
| `resolution` | 映射结局并公开允许内容 | 终局必需 |
| `debrief` | 真相和过程复盘 | 终局必需 |

迁移时不应先删除现有 reducer。应先把四相映射成兼容活动，再逐步让新包直接声明活动序列，最后删除 settlement-centric 的强制结构。

---

## 6. 内容发放：确定配置，不做 AI 语义搜证

正确的数据流是：

```text
YAML 声明发放点
       │
       ▼
程序确认活动门槛已满足
       │
       ├── 私有：按 character_id / member_id 投影角色章节与个人目标
       │
       └── 公开：向房间投影作者明确列出的材料
       ▼
客户端刷新快照或收到事件
```

不是：

```text
聊天文本 ──► LLM 猜测玩家发现了什么 ──► 自动加入线索库     [禁止]
玩家坐标 ──► 进入热点 ──► 才能发现关键证据                 [禁止]
```

当前 reducer 已经按 `stage_enter`、`all_players_read`、`settlement_done` 和 `outcome:*` 触发确定性材料公开，见 `engine/core/multiplayer_state_machine.py:590`。这是应保留的方向，但 `mode: none` 也会触发 legacy `settlement_done`；迁移到活动模型时应改成与实际活动完成点一致的中性命名。

但当前投影仍同时接受 `clue`、`evidence` 和 `media`，见 `engine/services/multiplayer_gameplay_service.py:481`；旧 `evidence` 概念仍和历史搜证模型纠缠。后续应保留“作者明确发放的线索卡/公共材料”，删除“通过场景、热点或动作发现 evidence”的获取模型。

建议目标写法：

```yaml
stage_rewards:
  private:
    investigator:
      - chapter-2
      - personal-mission-2
    insider:
      - chapter-2
      - personal-mission-2
  public:
    - clue-card-01
    - clue-card-02
    - witness-record
```

第一版不随机分配，不按人数平均切分一般材料。未来若需要角色定向材料，必须由作者显式声明接收角色，不能由运行时随机决定。

---

## 7. 受控 AI DM 的目标运行方式

当前 `engine/agents/dm_agent.py` 和 `engine/agents/hint_agent.py` 仍是两行占位文件。样例包新增的 `dm_guide/truth.yml` 已能支持终局复盘，但它不是可运行的 AI DM 主持脚本。固定 YAML 提示已有 reducer、command 和 snapshot 支持，不调用 LLM；但实际接线的 `MultiplayerMansionShell` 没有提示 UI，提示面板只存在于未接线的 `GameplayShell`，因此用户当前无法从真实场景路径使用该能力。

目标调用链应是：

```text
YAML: dm_checkpoint
       │
       ▼
程序构造受限输入
  - 当前阶段与活动
  - 当前已公开事实
  - 当前阶段私有主持稿
  - 有界讨论窗口 + 摘要
  - 已使用的提示层级
       │
       ▼
AI DM 生成“主持建议候选”
       │
       ▼
程序策略校验
  - 不含未授权事实
  - 不改变状态
  - 不代替玩家结论
  - 不越过提示层级
       │
       ▼
公开主持消息 / 建议继续讨论
```

建议 YAML 关联：

```yaml
dm_chapter:
  source: dm_scripts/chapter-01.md
  checkpoint: discussion-close
  guidance:
    allow_direct_answer: false
    use_progressive_hints: true
```

AI DM 的输入应使用“有界近期消息 + 稳定摘要”，而不是无限累积整局聊天。正式决策开始后，内容性提示关闭，只保留程序说明。

---

## 8. 沉浸舞台：保留空间，删除空间权威

目标边界非常简单：

```text
玩家移动 / 聚集 / 看到彼此
          │
          └── 只影响视觉、氛围和社交临场感

YAML 活动序列 ─────────── 独立控制读本、讨论、发放、决策和推进
```

### 8.1 应保留

- 可走动的共享舞台。
- 角色头像、朝向、移动动画与同伴位置。
- 用空间强化聚集感、距离感和场景氛围。
- 可从固定工具栏或阶段面板随时打开当前允许的玩法界面。

### 8.2 必须删除

- 进入坐标范围后才显示或解锁关键内容。
- 用热点触发角色章、线索、证据、NPC 对话或阶段推进。
- 以“调查/搜证”为通用主交互。
- 把世界坐标写进 YAML 活动完成条件。

### 8.3 当前实现的偏差

当前 `MultiplayerMansionShell` 仍把角色手记、公开档案、讨论室、圆桌判断和复盘映射成 `DemoSessionHotspot`，并通过 `MansionDemo.onInvestigate` 打开对应面板，见 `apps/web/components/multiplayer/MultiplayerMansionShell.tsx:62` 和 `:490`。角色手记已有固定 HUD 入口，讨论、判断和复盘也有 overlay 直达按钮；**公开材料目前仍只有热点入口**。因此问题不是所有活动都被位置锁住，而是公开材料确实被空间入口锁住，且整个多人壳层仍依赖 legacy hotspot 架构。

当前实现设置了 `includeDemoContent={false}`，避免直接复用旧 demo 证据内容，但还没有解除热点依赖。下一步应给公开材料增加始终可达的固定入口，并把所有舞台热点降级为可选的等价快捷入口；它们不得影响内容是否已发放、活动是否完成或阶段是否推进。

---

## 9. 断线、重连与恢复边界

核心规则：

> 网络程序可以恢复游戏，但不能替玩家推进游戏。

```text
玩家 B 断线
  │
  ├── 当前 YAML 活动不变
  ├── 玩家 A 仍可阅读和发送讨论消息
  ├── 所有“全员确认”门槛继续等待 B
  └── 不自动投票、不自动结束讨论、不自动进入下一阶段

玩家 B 重连
  │
  ▼
认证身份恢复 ──► 拉取权威快照 ──► 恢复私有投影与当前活动 ──► 继续
```

当前工作区已经具备一部分基础：

- 命令使用 `command_id`、`expected_revision` 和持久回执支持服务端幂等回放与 stale attempt reclaim。
- 状态、事件、命令回执和 outbox 表/批处理函数已有数据库验证。
- 客户端每 2 秒拉取权威快照，并在同步中断时保留上一次成功状态，见 `LobbyBoundary.tsx:20`。
- 客户端只会对 transport exception 用同一 UUID 自动重试一次；这不是跨刷新恢复 pending command。
- 空间位置通过独立 HTTP `PUT /scene-presence` 上报，不参与 reducer 门槛。

仍缺少：

- 认证 WebSocket 参与者绑定和房间事件订阅。
- 客户端 pending command/receipt 恢复，以及不确定 HTTP 5xx 后避免生成新 UUID 重复意图的策略。
- 客户端按事件序列 replay / gap detection / resync；当前 `room.resync` 忽略 `last_event_sequence`，只是 no-op。
- 多人 `/events` 的可用鉴权路径；当前路由最终只允许 legacy single session。
- 浏览器层面的断网、关闭标签页、重新进入后恢复验收。
- presence 与“玩家是否能继续玩法”的明确分离测试。

现有 `engine/api/websocket/handler.py:52` 仍只是未认证 `session.ping → session.pong` 心跳端点。虽然 contracts 中存在 WebSocket、snapshot 和 resync 类型，但不能把契约存在算作运行时完成。outbox 也尚未形成实时闭环：gameplay command 当前显式不写 outbox，batch dispatcher 没有具体 transport adapter、常驻 worker 或生产启动入口。

---

## 10. 当前实现状态：按能力严格判定

### 10.1 历史基线与依赖闭合候选的区别

| 能力 | `f9c8a4e` 历史基线 | `af79a9e` 依赖闭合候选 | 严格状态 |
|---|---|---|---|
| 离线多人 reducer | 已有固定四相 reducer 与聚焦测试 | 扩展到终局完成 | **已完成（reducer 范围）** |
| 建房、邀请、加入、选角、准备、开始 | 已有大厅前后端 | 增加统一持久命令路径 | **已完成** |
| 开始后的私有阅读 | 前端停在占位体验 | 已接入私有章节投影和全员读完门槛 | **已完成（候选基线）** |
| 公开讨论 | 契约/离线状态为主 | 已有持久讨论事件、HTTP 命令和双方 UI | **已完成（候选基线）** |
| 确定性公共材料 | reducer 已有核心逻辑 | 已接入快照和浏览器展示 | **已完成（候选基线）** |
| 阶段判断与推进 | reducer 已有 | 秘密提交、共享选择、阶段推进均接入 | **已完成（候选基线）** |
| 终局与复盘 | 样例曾被未支持 branch 阻断 | 严格双人包必须完整映射 ending、冻结 truth，并保证双方可打开复盘 | **严格双人 contract 已完成** |
| 完整双人浏览器通关 | 大厅验收止于活跃态 | 真实 Supabase/FastAPI/Next 双身份完整通关 | **已完成（候选基线）** |
| authoring schema 与 runtime 闭合 | 多人 schema 已存在 | 统一 playability 决策拒绝线性 executor 不消费或会破坏双人复盘的组合 | **严格双人 contract 已完成** |
| 样例内容一致性 | 双人样例已存在 | 第一阶段选项/结果 ID 与调查员章节陈述存在错误归因 | **部分完成** |
| 持久命令与数据库恢复 | 部分命令恢复基础 | 服务端回执、幂等、stale reclaim、attempt fencing 和权限已接通 | **已完成（服务端已测范围）** |
| outbox 实时投递 | 基础表/设计存在 | 表、事务写入与 batch dispatcher 存在；gameplay 不写 topic，且无 adapter/worker | **部分完成** |
| 固定协作提示 | reducer/contract 已有 | snapshot 和未接线 `GameplayShell` 有 UI；实际 Mansion shell 无提示入口 | **部分完成** |
| 共享舞台位置同步 | 未形成多人闭环 | HTTP presence、远端头像与在线新鲜度存在 | **部分完成** |
| 断线后浏览器恢复 | 有快照/重试设计 | HTTP 轮询可重新取得快照，但无 pending command、receipt 或专项浏览器恢复 | **部分完成** |
| multiplayer events / resync | contracts 存在 | `/events` 被 legacy 鉴权挡住，`room.resync` 忽略游标 | **仅契约/假实现** |
| 认证实时事件流 | contracts 存在 | 运行时仍只有 ping/pong；前端继续轮询 | **仅设计** |
| 未完成房间退出/释放 | 无 | `room.end_incomplete` 固定拒绝，弃局可能长期占用 principal reservation | **未开始** |
| 通用 `activities[]` | 无 | 仍是固定四相 | **未开始** |
| 受控 AI DM | 占位文件 | 只有固定提示和终局 truth，无 LLM 主持链路 | **未开始** |
| 个人目标自动判定 | 无 | 仍为角色剧本文本 | **暂停，不属于第一版** |
| 任意阶段分支 | 无 | 只支持 final judgment 选择 ending；一般 branch 仍拒绝 | **暂停** |
| 单人多 NPC 智能体 | 旧系统仍有实现 | 仍有 NPC provider/agent 和旧入口 | **暂停或移出当前方向** |
| 地图搜证与热点推进 | 旧 demo 主路径 | 多人 UI 仍复用 hotspot 架构，公开材料只有热点入口 | **移出方向，但清理未完成** |

### 10.2 当前可玩的真实边界

当前双人样例可以完成：

```text
创建房间
  → 邀请第二名匿名玩家
  → 双方选角并准备
  → 开始
  → 私有角色章节
  → 确定性公开材料
  → 公开讨论
  → 双方确认结束讨论
  → 秘密判断并揭晓
  → 进入下一章节
  → 终局共享判断
  → ending 映射
  → 完整复盘
```

该闭环由 `engine/services/multiplayer_gameplay_service.py:113` 接收玩法命令并构造参与者安全快照，由 `LobbyBoundary.tsx:86` 切换到活跃游戏界面。终局通过 `ending_by_outcome` 将最终 `outcome_id` 解析为作者声明的 ending 并把房间标为 `completed`；两类 ID 不再要求同名。导入、发布、房间创建和冻结版本快照解码共同消费 `multiplayer_package_playability`，在写入或开局前拒绝不可完成的多人剧本版本。

必须同时写清限制：

- 只验证了严格双人包，不是任意人数通用引擎。
- 流程仍强制四相，第一阶段样例投票只是剧本特例。
- 传输依赖 2 秒 HTTP 轮询，不是实时事件流。
- 空间交互仍使用旧 hotspot 抽象。
- AI DM 没有进入任何可玩路径。
- 当前提交是后续建设基线，不代表任意人数、任意剧本或实时多人产品已经完成。

### 10.3 已闭合的严格双人 package contract

`multiplayer_package_playability` 现在是导入、发布、房间创建和冻结版本解码共同消费的不可变决定。当前被接受的版本必须满足：

- 恰好两个 playable character，且每个阶段的角色集合完全一致；
- stage index 顺序唯一，存在的 act 阶段顺序与其一致，`engine.entry_stage` 指向首阶段，transition 只指向相邻下一阶段；跳跃、回退、entry/exit conditions 和未消费的 legacy stage capability 必须关闭或为空；
- 第一阶段角色章节使用 `game_start`，后续章节使用匹配当前阶段的 `stage_enter` 和 `stage_min`；章节不得复用或游离于阶段映射之外；
- 必须存在冻结 truth 且包含非空 `case_summary`；shared-choice 终局只能使用 `outcome_only`；每个最终 outcome 显式映射到唯一 authored ending；
- 多人包不接受 `engine.default_ending`，ending 的 legacy condition/action/rating bonus 只能保留不会产生行为的固定占位值；
- 唯一 `final_judgment` 必须位于线性末端，且完成后的同一冻结版本能分别为两名参与者生成 participant-safe review。

这使包作者能够依赖当前严格双人线性契约，但不代表广义 schema 中的任意人数、任意分支或 legacy 单人能力已被多人 runtime 支持。样例中调查选项与角色文字之间的语义归因仍是独立的内容一致性问题，不是 contract/runtime 闭合问题。

---

## 11. 当前运行架构与目标架构

### 11.1 当前依赖闭合候选基线

```text
┌──────────────── Browser A ────────────────┐
│ 匿名 JWT                                  │
│ HTTP command + 2s snapshot polling        │
│ scene-presence PUT                        │
└──────────────────┬────────────────────────┘
                   │
┌──────────────────▼────────────────────────┐
│ FastAPI                                    │
│ room service + gameplay service            │
│ participant-safe snapshot/review projection│
└──────────────────┬────────────────────────┘
                   │ transaction
┌──────────────────▼────────────────────────┐
│ PostgreSQL / Supabase                      │
│ room state + events + command receipts     │
│ checkpoint writes + outbox + presence      │
└──────────────────┬────────────────────────┘
                   │ outbox batch dispatcher + Publisher Protocol
                   ▼
        [无具体传输 adapter、常驻 worker 或浏览器订阅通道]

Browser B 通过相同 HTTP 路径独立轮询。
```

这里的 outbox 仍是基础设施，不是已上线事件总线：当前 gameplay 命令显式关闭 outbox topic，`publish_room_outbox_batch()` 也没有 transport adapter、常驻 worker 或 lifespan 接线。快照投影每 2 秒从 sequence 0 读取完整事件历史，completed 页面仍持续轮询，因此讨论历史增长后会产生线性放大成本。

### 11.2 目标多人运行架构

```text
HTTP durable command ──► 权限 / 幂等 / reducer / transaction
                                      │
                                      ├── state projection
                                      ├── ordered room event
                                      └── outbox
                                           │
                                           ▼
认证房间事件流 ◄── replay / sequence / resync ◄── Browser A / B
       │
       └── 断线后：先快照，再从 event_head_sequence 续播
```

HTTP 应继续承担可靠命令提交和快照恢复；WebSocket 用于低延迟通知、presence 和事件推送，不应成为唯一权威状态来源。

---

## 12. 保留、删除、暂停与后续建设

### 12.1 保留并继续加固

| 能力 | 原因 |
|---|---|
| 房间、邀请、选角、准备、开始 | 已形成真实多人入口 |
| 持久命令、revision、幂等回执 | 是可靠多人执行的基础 |
| 事务状态、事件日志与 outbox schema/dispatcher | 支持恢复、审计和未来实时流，但仍需 gameplay 接线与生产 worker |
| 参与者安全快照 | 保护私有章节和秘密提交 |
| 有序 stage index | 可以作为线性流程基础 |
| 确定性材料发放 | 符合 YAML 创作权边界 |
| 私有角色章节与叙事目标 | 符合多人信息不对称核心 |
| 终局 ending 和复盘投影 | 构成完整体验闭环 |
| Mansion 移动、渲染、头像和位置 | 保留沉浸与社交临场感 |

### 12.2 删除或解除耦合

| 旧概念 | 要删除的不是 | 真正要删除的内容 |
|---|---|---|
| 地图搜证 | 整个可走动舞台 | 坐标/热点决定内容获取和流程推进 |
| clue | 作者发放的线索卡 | 通过搜索动作“发现 clue”的运行时模型 |
| evidence | 终局可展示的材料文本 | `scene_id + hotspot_id` 发现证据的 API、loader、状态和 UI |
| hotspot | 纯装饰或等价快捷入口 | 作为角色章、讨论、决策的唯一入口 |
| NPC | 将来可能的演绎扩展 | 当前单人多 NPC 主产品入口与默认依赖 |
| action schema | 通用命令概念 | 搜索、调查 NPC、发现 evidence 的旧公共 API |

清理必须覆盖：

- `engine/core/package_content_yaml.py` 中场景搜证与 evidence 发现结构。
- `engine/core/package_stage_yaml.py` 中旧 actions/scenes/clue-round/NPC 强耦合。
- `engine/api/schemas/actions.py` 中 scene、hotspot、evidence 和 NPC 动作。
- `MansionDemo` 与多人壳层之间的 `onInvestigate` 玩法耦合。
- `/library`、demo 和 snow-village 主入口对旧产品方向的宣传。
- 相关 fixture、测试、文档和类型，不留下不可达死代码。

### 12.3 暂停

- 单人 NPC 多智能体玩法。
- NPC 自主行动和 NPC 记忆编排。
- 任意图分支和复杂回跳。
- 自动评估个人任务完成度。
- 搜索、机关、表演等剧本特定机制的通用引擎化。
- 多轮投票和平票策略的通用化；只有具体剧本声明时才实现。

### 12.4 下一步必须建设

1. 修复 final judgment、终局拓扑、shared reveal、truth 必需性、角色数量、ending 映射和章节 release 的 schema/runtime 闭合问题，并修正样例选项的错误归因。
2. 解除多人玩法与空间热点的依赖，并给公开材料增加固定入口。
3. 将提示 UI 合并进实际接线的场景壳，删除未接线 `GameplayShell` 的重复实现。
4. 增加断线、5xx 不确定结果、重开页面、pending command/receipt 恢复和继续全员门槛的浏览器验收。
5. 让 gameplay 写入 outbox，补生产 dispatcher/adapter，打通 multiplayer events 鉴权并实现 sequence gap / replay / resync。
6. 将快照事件读取改为增量或有界投影，completed 后停止无意义轮询；增加弃局/关闭房间与 reservation 释放。
7. 引入兼容式 `activities[]`，不再假设每阶段有 settlement。
8. 为样例包增加分阶段私有 DM 主持稿与 checkpoint 声明，并实现受控 AI DM 调用、输入裁剪、输出策略校验和审计记录。
9. 删除旧搜证/NPC 产品入口及其依赖链。

---

## 13. 依赖顺序路线图

```text
R0  收紧候选垂直切片
 │  - 让 authoring schema 与 runtime/review 完全闭合
 │  - 修正样例选项和结果语义
 │  - 保持全部真实栈门禁
 ▼
R1  纠正空间与实际 UI 边界
 │  - 当前活动始终可达，公开材料不再被热点锁住
 │  - 位置只做 presentation/presence
 │  - 提示 UI 合入实际 shell，删除重复 shell
 ▼
R2  恢复与实时同步
 │  - pending command / 5xx / reconnect 浏览器验收
 │  - gameplay outbox → worker → authenticated room events
 │  - snapshot + cursor replay + gap resync
 │  - bounded event projection + completed stop-poll
 │  - abandon/close + reservation release
 ▼
R3  通用活动模型
 │  - 四相兼容适配器
 │  - activities[] runtime
 │  - optional decision / performance / checkpoint
 ▼
R4  受控 AI DM
 │  - 私有主持稿
 │  - checkpoint invocation
 │  - bounded context + policy validator
 │  - no state mutation
 ▼
R5  旧方向物理清理
    - search/hotspot/evidence discovery API
    - NPC-first product entry
    - stale docs, fixtures and tests
```

顺序不能倒置。特别是：

- 不应先让 AI DM 上线，再补状态边界。
- 不应先扩展任意分支，再解决线性活动模型。
- 不应为了删除搜证而删除整个空间渲染能力。
- 不应把 WebSocket 当状态权威；先保留可靠 HTTP 命令和快照恢复。

---

## 14. 验证记录

T01 候选闭包与本次场景重构在本地工作树运行的验证结果如下：

| 验证 | 结果 | 说明 |
|---|---|---|
| `uv run --frozen pytest engine/tests/ -q` | **499 passed, 16 skipped** | 16 项均为显式数据库环境门禁 |
| `make test-durable-commands` | **22 passed** | 覆盖命令幂等、持久拒绝、事务回滚、stale reclaim、outbox、数据库权限和双人 HTTP 通关 |
| `make test-checkpoint-recovery` | **1 passed** | 覆盖 worker 被强杀后的 checkpoint 恢复 |
| 聚焦多人后端测试 | **76 passed, 12 skipped** | 未提供数据库 URL 时命令 HTTP 集成按设计跳过 |
| route-mocked Playwright | **8 passed** | 命令恢复、事件 gap、大厅启动与活跃游戏私有投影浏览器契约 |
| `make test-mp2-live` | **1 passed** | 真实 Supabase + FastAPI + Next，双匿名身份完成候选游戏和复盘 |
| `npm --prefix apps/web run lint` | **通过** | ESLint 无错误 |
| `npm --prefix apps/web run build` | **通过** | Next 15 生产构建和类型检查成功 |
| 聚焦 `ruff check` | **通过** | 多人后端变更无 lint 错误 |
| 聚焦 `basedpyright` | **0 errors** | 多人后端类型检查通过 |
| `git diff --check` | **通过** | 当前跟踪差异无空白错误 |

这些结果支持“当前双人候选垂直切片已可完整操作”的结论，但不支持以下结论：

- 不支持宣称 AI DM 已实现。
- 不支持宣称 WebSocket 多人运行时已实现。
- 不支持宣称任意人数、任意剧本和任意活动都可运行。
- 不覆盖实际 Mansion shell 的提示 UI、浏览器断线恢复、5xx 不确定命令结果、multiplayer `/events` 鉴权、生产 outbox worker、长讨论历史轮询成本或弃局释放。
- `engine/tests/test_checkpoint.py` 当前被删除；仍需说明其旧 round-trip 覆盖由哪些现有测试替代，不能只用进程强杀恢复测试默认代替全部语义。
- 不支持宣称旧搜证方向已从代码中清理完成。
- 不支持把严格双人候选基线描述为任意剧本可用的稳定多人产品。

---

## 15. 剧本行业流程校准

公开资料与从业实践显示，常见流程大体是：

```text
组局 / 分角
  → 私有读本
  → 自我介绍
  → 一轮或多轮讨论与信息发放
  → 可选搜证、私聊、小剧场或特殊机制
  → 可选终局判断 / 投票
  → 真相揭晓
  → DM 复盘
```

这说明：

- 搜证是常见剧本形式，但不是平台底层必需能力。
- 最终投票在推凶类剧本中常见，但不是每阶段统一动作。
- 多轮票、票数、弃权和平票都应由具体剧本或主持手册声明。
- DM 的常见职责是准备、讲解、控节奏、发放作者允许的信息、答疑和复盘，不是替玩家选择结论。
- 现行监管文件要求经营备案、内容自审、适龄提示、安全告知等，不统一规定主持步骤、投票轮次或平票规则。

因此，平台底层应实现“通用活动 + 可选机制”，而不是把某一种线下推凶流程写死成所有剧本的标准。

参考资料：

- [文化和旅游部等五部门关于加强剧本娱乐经营场所管理的通知](https://www.gov.cn/zhengce/zhengceku/2022-06/27/content_5698021.htm)
- [文化和旅游部通知页面](https://www.mct.gov.cn/whzx/bnsj/jdgls/202207/t20220701_934431.html)
- [广州剧本娱乐经营场所管理办法](https://www.gz.gov.cn/zwgk/gzsrmzfgbn/2023/8/content/post_10640172.html)
- [央视：剧本娱乐行业与主持人工作](https://news.cctv.com/2022/06/08/ARTIIuaeBqXhXcteDncrTGZz220608.shtml)
- [中新网：剧本杀 DM 职业观察](http://www.chinanews.com.cn/gsztc/2022/07-24/9811033.shtml)
- [搜狐：七阶段剧本杀流程](https://www.sohu.com/a/452894146_141588)
- [百变大侦探官方产品页](https://sj.qq.com/appdetail/com.mszmapp.detective)
- [线上剧本杀产品流程分析](https://www.woshipm.com/evaluating/4533914.html)

---

## 16. 文档治理与完成定义

2026-07-26 文档整理已解决以下冲突（原审计列出）：

- `README.md` 已重写为多人优先的产品描述，并链接本总览为状态权威。
- 新增 `docs/README.md` 索引，明确各文档的权威级别与阅读顺序。
- `MULTIPLAYER_ARCHITECTURE_PLAN.md` 已标注为历史设计，移除对已删除 ADR/报告的链接。
- `ARCHITECTURE_OVERVIEW.md`、`EXECUTION_PLAN.md`、`FRONTEND_EXPERIENCE_DESIGN.md`、
  `SONNET5_HANDOFF.md` 均已加历史定位说明。
- `API_REFERENCE.md` 已声明只覆盖单人接口；`SCRIPT_PACKAGE_SCHEMA.md` 已更新为
  loader 现已接受多人字段并链接 10.3 节缺口清单；`CONDITION_DSL_REFERENCE.md`
  已声明适用范围为单人路径。
- `openwiki/quickstart.md` 已补 presence 状态行；`openwiki/architecture/system.md`
  和 `backend.md` 已改为“`/events` page 仅限 legacy single session”。

后续里程碑不能再用“文件已创建”或“契约已定义”作为完成标准。每个里程碑至少要留下：

- 可追溯的产品边界。
- 前后端真实闭环。
- 参与者安全与权限测试。
- 状态机和持久化测试。
- 浏览器用户路径验收。
- 若依赖数据库或实时服务，必须有真实环境门禁。
- 已知限制和未实现项，不能藏在 TODO 或历史报告中。

本文档本身不代表清理已经完成。它建立的是之后判断实现是否正确的共同尺度：

```text
多人真人讨论是核心
YAML 编排内容
程序掌握执行
AI DM 受限主持
玩家决定结论
空间只提供临场感
网络只能恢复，不能代替玩家推进
```
