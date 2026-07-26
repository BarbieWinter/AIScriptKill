# docs 索引

本目录保存**项目级总设计与状态文档**。细分实现知识（当前结构、边界、工作流、运维）
写在 [`openwiki/`](../openwiki/quickstart.md)，不在这里；本目录也不设 ADR 或阶段报告。

## 冲突裁决顺序

1. 可执行源码、迁移与测试。
2. [`PRODUCT_DIRECTION_AND_IMPLEMENTATION_STATUS.md`](PRODUCT_DIRECTION_AND_IMPLEMENTATION_STATUS.md) —— 产品边界与路线判断的权威。
3. [`../CONTEXT.md`](../CONTEXT.md) —— 领域术语不变量。
4. OpenWiki 当前实现指南。
5. 本目录其余设计文档（表达设计意图，不证明实现状态）。

## 文档清单

### 当前权威

| 文档 | 内容 | 状态 |
|---|---|---|
| [PRODUCT_DIRECTION_AND_IMPLEMENTATION_STATUS.md](PRODUCT_DIRECTION_AND_IMPLEMENTATION_STATUS.md) | 最终产品定义、四类权威边界、逐能力完成度、保留/删除/暂停清单与依赖顺序路线图 | **权威**（审计基线 2026-07-27） |
| [../CONTEXT.md](../CONTEXT.md) | 多人剧本杀领域术语表：房间、阶段、结算、DM 边界等 | **权威** |

### 有效参考（描述当前实现的一部分）

| 文档 | 内容 | 注意 |
|---|---|---|
| [API_REFERENCE.md](API_REFERENCE.md) | 单人 REST 与 WebSocket 契约 | 多人接口边界见 OpenWiki backend 指南与运行中的 OpenAPI |
| [SCRIPT_PACKAGE_SCHEMA.md](SCRIPT_PACKAGE_SCHEMA.md) | 剧本包目录结构与 YAML Schema | 当前执行边界见 OpenWiki script-gameplay 指南 |
| [CONDITION_DSL_REFERENCE.md](CONDITION_DSL_REFERENCE.md) | 单人条件 DSL 完整参考 | 多人确定性运行契约见 OpenWiki script-gameplay 指南 |

### 历史设计（保留意图与背景，不代表当前实现或计划）

| 文档 | 内容 | 为何保留 |
|---|---|---|
| [MULTIPLAYER_ARCHITECTURE_PLAN.md](MULTIPLAYER_ARCHITECTURE_PLAN.md) | 多人 v1 目标架构与 MP-0～MP-8 执行计划 | 目标架构章节（命令信封、WebSocket、恢复协议）仍是后续建设蓝本；任务进度与状态标记已过期 |
| [ARCHITECTURE_OVERVIEW.md](ARCHITECTURE_OVERVIEW.md) | 最初单人多 NPC 方向的系统架构总览 | 引擎/剧本分离、数据权限模型等原则仍适用；单人 Agent 玩法已移出当前方向 |
| [EXECUTION_PLAN.md](EXECUTION_PLAN.md) | 原始 T-1～T-5 任务拆解 | 任务历史与通用执行要求（附录 B）仍有参考价值 |
| [FRONTEND_EXPERIENCE_DESIGN.md](FRONTEND_EXPERIENCE_DESIGN.md) | 单人"互动电影"前端体验设计 | 视觉氛围与沉浸原则仍指导多人舞台；页面结构对应旧单人产品 |
| [SONNET5_HANDOFF.md](SONNET5_HANDOFF.md) | 旧单人前端实现任务书 | 仅历史记录 |
| `aiscriptkill.clapet.json` | 早期架构图（clapet.app 格式） | 对应旧单人架构，未随多人方向更新 |

## 推荐阅读顺序

新人接手：

1. [`../README.md`](../README.md) —— 项目是什么、怎么跑起来。
2. [`PRODUCT_DIRECTION_AND_IMPLEMENTATION_STATUS.md`](PRODUCT_DIRECTION_AND_IMPLEMENTATION_STATUS.md) —— 现在走到哪、要做成什么、下一步顺序。
3. [`../CONTEXT.md`](../CONTEXT.md) —— 统一术语。
4. [`../openwiki/quickstart.md`](../openwiki/quickstart.md) —— 按任务找到源码与验证入口。

写剧本包：[`SCRIPT_PACKAGE_SCHEMA.md`](SCRIPT_PACKAGE_SCHEMA.md)（注意文首当前内容快照说明）。

做多人后续建设：先读状态权威文档第 12–13 节（保留/删除清单与路线图），再参考
[`MULTIPLAYER_ARCHITECTURE_PLAN.md`](MULTIPLAYER_ARCHITECTURE_PLAN.md) 的目标架构章节。
