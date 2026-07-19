# MP-1 无网络多人阶段状态机验证报告

> 日期：2026-07-18
> 源码基线：`bae4a55a6bd705455ee17ac65d9357dc7482dcbb`
> 开发分支：`feature/mp-1-offline-state-machine`
> 隔离工作树：`/private/tmp/aiscriptkill-mp1-offline-state-machine`
> 提交状态：未 commit、未 push

## 1. 判定

```text
MP-1 offline state machine       PASS
Multiplayer package integration  PASS
Privacy and deterministic flow   PASS
Legacy single-player regression  PASS
Frontend lint/build              PASS
Real PostgreSQL lane             BLOCKED / NOT RUN
MP-2 room/database/runtime       NOT IMPLEMENTED
```

MP-1 已完成。该判定只覆盖真实双人 fixture、multiplayer authoring loader 接线、纯同步
`GameStateV2` reducer、participant-scoped snapshot 和 headless tests；不代表房间、数据库、
HTTP/WebSocket runtime、双浏览器 UI 或公共 AI DM 已实现。

## 2. 实现范围

### 双人 fixture

新增 `script-packages/mp1-two-player/`：

- 恰好两个可玩角色。
- 每个角色各有 investigation 与 final-judgment 两章私有剧本。
- 一方剧本明确允许隐瞒事实，且该文本不会进入公共 package/stage/character 投影。
- investigation 使用秘密投票；final-judgment 使用共同选择。
- 包含 `stage_enter`、`all_players_read` 公共材料和三级提示。

### Loader 与跨文件验证

- `package.yml` 可声明 strict `multiplayer` policy。
- multiplayer stage 的 chapters、public materials、discussion、settlement、hints 通过现有 directory/ZIP loader 归一化。
- 校验玩家范围、可玩角色数、角色章节 owner/覆盖、公共材料存在性、material namespace 互斥和当前阶段 outcome trigger。
- 未声明 multiplayer policy 的 legacy package 仍拒绝 flat multiplayer-only 字段。

### 纯 reducer 与隐私投影

- `initialize_stage_runtime()` 初始化阶段公共进度。
- `reduce_stage_command()` 纯同步处理 read/discussion/settlement/hint 命令，不访问网络、数据库、repository 或 LangGraph。
- `enter_next_stage()` 是可信系统入口；active settlement 必须全部提交、已揭晓并拥有 outcome，不能仅伪造 REVEAL phase 绕过结算。
- secret submission 在完成前只存在对应成员的 `PrivatePlayerState`。
- `build_participant_snapshot()` 只投影目标成员的 private state。
- 结算公开模式彼此可区分：named ballots、aggregate counts、outcome only。
- aggregate counts 按创作选项顺序输出并包含零票选项。
- reducer 不修改 `room_revision`，也不原地修改输入状态。

## 3. 验证结果

| Lane | 命令/范围 | 结果 | 细节 |
|---|---|---|---|
| Tools | `make verify-dev-tools` | PASS | pytest 9.1.1、Ruff 0.15.20、BasedPyright 1.39.9。 |
| Focused MP-1/MP-0 | loader、reducer、contracts、authoring、flags、restore | PASS | 55 passed；0.85s。 |
| Reducer focused | `test_multiplayer_offline_state_machine.py` | PASS | 17 passed。 |
| Multiplayer set | loader + reducer + multiplayer contracts | PASS | 35 passed。 |
| Backend tests | `pytest engine/tests -q` | PASS / SKIP | 406 collected；404 passed，2 skipped；5.89s。 |
| Snow + RAG | 5 个专项测试文件 | PASS | 20 passed；2.55s。 |
| Ruff check | full repository | PASS | `All checks passed!`。 |
| MP-1 format | 变更 Python 文件 | PASS | 全部已格式化。 |
| Full format | full repository | BASELINE FAIL | 仍只有 MP-0 报告记录的 10 个历史文件需格式化。 |
| MP-1 production types | contracts + reducer + loader integration | PASS | 0 errors，0 warnings，0 notes。 |
| Production BasedPyright | Makefile 等价生产范围 | BASELINE FAIL | 仍只有 `runtime_action_mappers.py:232-249` 的历史 10 errors。 |
| Web lint | `npm --prefix apps/web run lint` | PASS | ESLint 无错误。 |
| Web build | live mode Next build | PASS | Next.js 15.5.20；全部路由构建成功。 |
| Diff whitespace | `git diff --check` | PASS | 无 whitespace error。 |
| Local DB | `docker info` | BLOCKED | 无法连接 Colima Docker socket。 |
| DB privilege/recovery | PostgreSQL probes | NOT RUN | Docker daemon 不可用；默认 suite 的 2 skips 不代表数据库通过。 |

## 4. Headless 行为 Gate

- [x] 单人读完不能提前进入讨论；read intent 可撤销。
- [x] 全员读完后才原子进入 DISCUSS。
- [x] discussion close 需要全员确认，完成前可撤销。
- [x] 无 settlement 阶段结束讨论后进入可观察 REVEAL。
- [x] 部分秘密提交只公开 submitted member IDs，不公开 option。
- [x] named ballots 按 canonical required-member 顺序公开。
- [x] aggregate counts 按 authored option 顺序公开并包含零票项。
- [x] outcome-only 不公开 ballots 或 counts。
- [x] deterministic tie 只使用 YAML 显式 tie outcome。
- [x] A→B 与 B→A 得到完全等价的最终状态。
- [x] shared candidate 切换会重置确认集合为新提议者。
- [x] final judgment 按 authored answer mode 分派。
- [x] hints 仅在 DISCUSS 中按 1→2→3 且经全员确认揭晓。
- [x] 伪造 REVEAL phase 不能绕过未完成 settlement。
- [x] 合法 no-settlement REVEAL 可以进入下一阶段。
- [x] 下一阶段只解锁对应角色章节，不泄漏另一成员私有内容。
- [x] canonical required-member 集合与 room revision 在 reducer 中保持不变。
- [x] Snow Village legacy single-player package shape 不变。

## 5. 已知基线与环境阻断

全仓 Ruff format 仍报告 MP-0 基线中的同一组 10 个历史文件；MP-1 变更文件单独检查通过。
生产 BasedPyright 仍报告 `engine/services/runtime_action_mappers.py:232-249` 的同一组 10 个历史
错误；MP-1 production files 为 0 errors。两者均未因 MP-1 扩大失败集合。

本机 Colima Docker daemon 不可连接，因此真实 PostgreSQL privilege 与 SIGKILL recovery lanes
保持 `BLOCKED / NOT RUN`。MP-1 reducer 本身不访问数据库，但该环境阻断仍必须在后续发布
判定中保留，不能把默认 pytest 的两个 skip 写成数据库通过。

## 6. 下一阶段边界

MP-2 才开始实现房间、身份、邀请、选角、ready/start、migrations 和 repository。MP-1 不开放
多人 route，不增加 WebSocket runtime，不实现 command idempotency/outbox/replay，也不接公共 AI DM。
