# 剧本与玩法领域

```text
┌─ OPENWIKI PAGE ──────────────────────────────────────────────────────────────┐
│ KIND      reference                                                          │
│ SCOPE     Domain rules, package lifecycle, single and multiplayer gameplay   │
│ VERIFIED  2026-07-22 @ WORKTREE                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

[Home](../quickstart.md) / **Domain** / **Gameplay and Packages**

本页维护当前领域规则和剧本包工作流；AI 负责受控表达，不拥有事实写权限。

## 产品边界

AI 可以：

- 扮演当前阶段允许的 NPC 或公共 DM 表达层。
- 使用经过阶段、角色和 discovery 权限过滤的知识。
- 在固定事实边界内调整措辞、节奏和提示表达。

AI 不可以：

- 改变凶手、动机、关键证据、正确结局或 authored outcome。
- 泄露其他角色章节、未来阶段、DM truth 或未揭晓 submission。
- 直接决定解锁、阶段推进、结算或 canonical state patch。

[SECURITY] 规则由 package、条件、事件、reducer 和服务端投影执行，不能依赖
prompt 自律替代授权。

## 剧本包

```text
package.yml
stages/
characters/
character_scripts/        optional private chapters
clues/                    optional
scenes/                   optional
evidences/                optional
media/                    optional
endings.yml               optional
DM guide files            optional server-only truth
assets/                   optional
```

加载流程：

```text
zip or directory
  -> strict archive and YAML/Markdown parsing
  -> stable records
  -> ID/reference/asset validation
  -> multiplayer-specific validation when enabled
  -> optional asset upload
  -> normalized database import or immutable room snapshot
```

必需内容是 `package.yml`、至少一个 stage 和至少一个 character。严格模型拒绝
未知字段；缺失引用、重复 ID、非法素材路径和不支持的动作会阻止导入。

## 当前内容

### `snow-village`

- [LIVE] 单人垂直切片，`max_players: 1`。
- 玩家角色：`zhuosiyuan`；NPC：`wangdada`。
- 四个阶段、两个场景、一条线索、一件证据和两个私有章节。
- Live action 由 YAML/StateGraph 执行；Mock 故事不是权威内容。
- `endings.yml` 当前为空；单人最终提交仍走 legacy review 持久化路径。

### `mp1-two-player`

- [LIVE] Slim M2 双人机制包，可通过真实 HTTP polling 浏览器流程完成一局。
- [M3 CANDIDATE] 私有时间线已改为双向互补；秘密投票改为假设选择，终判明确责任边界。
- 角色：`investigator` 与 `insider`，每人两个私有章节。
- investigation：读本、来源核对清单、讨论、secret vote、reveal、同步推进。
- final judgment：shared choice、`outcome_only`、完成时公开案件重建与所选结局材料。
- 两个 authored endings，加上 completed-only DM truth 与隐藏时间线。
- 当前内容目标时长 20 分钟；是否形成真实信息交换仍必须通过下方真人 gate。

## 单人玩法

```text
library
  -> package details
  -> character selection
  -> create session
  -> read chapter / inspect / talk / show evidence
  -> request stage advance
  -> final submission
  -> persisted review
```

单人 StateGraph 校验 action 和 target，执行 authored event/condition，保存 checkpoint，
再投影 session、chat 和 discoveries。角色章节只向当前角色发放，并从 `unlocked`
单调升级到 `viewed`。

## 双人玩法

```text
create room
  -> invite second participant
  -> unique character assignment
  -> all ready / host start
  -> read confirmation barrier
  -> public discussion
  -> deterministic settlement
  -> synchronized stage advance
  -> final shared judgment
  -> authored ending
  -> completed-only review
```

当前 reducer 语义：

- 读本确认提交后锁定，不提供 `stage.revoke_read`。
- discussion close 在全员确认前可以撤销。
- shared choice 可更换候选；更换会重置之前确认。
- secret vote 的 reveal 只能达到 authored policy 指定的粒度。
- final settlement outcome 直接选择同 ID ending，不引入通用 branch graph。
- `completed` 必须拥有与 revealed final outcome 一致的 `ending_id`。

## Reveal 与复盘

| Reveal policy | 可公开事实 | 禁止升级 |
|---|---|---|
| `named_ballots` | 玩家与选项 | 不附加私有 payload |
| `aggregate` | 选项计数 | 不推出实名票型 |
| `outcome_only` | outcome | 不返回 ballots/counts |

多人复盘要求：

1. room 已完成；
2. 请求者属于 room；
3. final definition 与完成态匹配；
4. ending、章节和 truth 来自 room frozen package；
5. settlement facts 保持 authored reveal 粒度。

当前 canonical state 只保存当前阶段。若未来需要跨阶段关键记录，应在 reveal 时
持久化已裁剪 facts，不能从私有命令事后重建。

## Slim M3 真人试玩

Slim M3 验证的是“两个第一次接触该剧本的人是否能自行完成并产生有价值的讨论”，
不是继续扩建传输或运行基础设施。自动化只证明技术闭环，不能替代本节证据。

### 单轮协议

- 两名玩家此前没有阅读 `mp1-two-player`、测试或完整真相。
- 使用两个隔离浏览器身份和各自屏幕；不得互看角色章节。
- 一名观察者只处理登录、网络或页面崩溃，不解释规则、答案或下一步操作。
- 从 `/multiplayer` 开始，到 completed review 出现为止，全程记录阶段时间点。
- 玩家可以自由聊天；观察者不要求固定话术或强制消息数量。
- 完成后分别作答，再共同讨论，避免一人的反馈覆盖另一人。

记录模板：

```text
设备 / 浏览器：
创建 -> 加入：
大厅 -> 开始：
第一章 read / discuss / settle / reveal：
第二章 read / discuss / settle / completed：
技术中断：
请求指导次数与原话：
明显犹豫或误点：
形成分歧的私有信息：
改变判断的公开材料或对方陈述：
是否看到不应提前出现的内容：
总时长：
```

### 分别访谈

每名玩家独立回答：

1. 你在每个阶段是否知道下一步要做什么？哪一刻最不清楚？
2. 哪条只有你知道的信息值得隐瞒、转述或拿来质疑对方？
3. 对方说了什么让你改变或重新检查判断？
4. 第一次投票和最终共同判断是否有真实取舍，还是答案显而易见？
5. 等待另一位玩家时，页面是否清楚说明正在等什么？
6. 你是否在复盘前看到了另一角色原文、未揭晓选择或案件真相？
7. 你愿意再玩一个同样结构但不同案件的双人剧本吗？为什么？

量表使用 1～5 分：流程清晰度、讨论价值、判断张力、节奏、继续游玩意愿。

### M3 gate

一轮记为技术有效，必须满足：

- 两名玩家都从真实入口完成到复盘，且没有观察者提供玩法指导。
- 没有私有章节、未揭晓选择或完整真相提前串线。
- 任一刷新或短暂等待没有造成身份、阶段或已提交状态丢失。
- 观察记录完整，不能只保存最终评分。

产品 gate 需要至少两轮有效试玩、共四名首次玩家，并满足：

- 每轮双方都能说出至少一项由对方陈述带来的新信息或判断变化。
- 没有重复出现的“完全不知道下一步”阻塞；若出现，先修复再重新计轮。
- 四名玩家的流程清晰度均不低于 4/5。
- 至少三名玩家的讨论价值和继续游玩意愿不低于 4/5。
- 第一次投票或最终判断不能被所有玩家描述为“不讨论也能直接点”。

[CAUTION] 通过上述 gate 只支持当前双人结构继续迭代，不证明 WebSocket、地图、
AI DM、多实例或更多玩家规模已经必要。

## 条件、事件与 AI

- 条件 DSL 和事件动作由 loader 在导入期校验。
- StateGraph/reducer 是阶段推进和结算权威。
- RAG 只返回当前 session 已授权的知识片段。
- NPC 生成失败或输出越界时使用确定性 fallback。
- 公共 AI DM 仍是 `[PLANNED]`，不是双人通关依赖。

## 边界

- **包含：** 领域不变量、内容结构、导入、玩法和复盘语义。
- **不包含：** 完整 YAML schema、API endpoint 清单或 UI 组件设计。
- [SECURITY] **私密内容** — 角色章节、truth 和 submission 不进入公共 snapshot。
- [CAUTION] **完成证明** — live-stack PASS 证明技术闭环，不代表目标玩家觉得内容有趣。

## 变更导航

| 修改目标 | 首先查看 | 验证入口 |
|---|---|---|
| Package schema | `engine/core/package_*` | package loader tests |
| 单人内容 | `script-packages/snow-village` | core vertical slice tests |
| 双人内容 | `script-packages/mp1-two-player` | real package flow test |
| 多人规则 | `multiplayer_state_machine.py` | offline state-machine tests |
| 双人运行与投影 | `multiplayer_gameplay_service.py` | gameplay service + durable HTTP tests |
| 完成复盘 | `multiplayer_review.py` | real package flow + live browser test |

## 权威来源

- **内容：** `script-packages/`。
- **加载：** `engine/core/package_loader.py` 与 `engine/core/package_*`。
- **单人运行：** `engine/core/script_engine.py`。
- **多人运行：** `engine/core/multiplayer_state_machine.py`。
- **总设计：** `docs/SCRIPT_PACKAGE_SCHEMA.md` 与条件 DSL 设计文档。

---

[Previous: Frontend](../architecture/frontend.md) · [Home](../quickstart.md) ·
[Next: Operations](../operations/data-and-deployment.md)
