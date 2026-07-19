# MP-0 基线报告

> 日期：2026-07-17
> 源码基线：`bae4a55a6bd705455ee17ac65d9357dc7482dcbb`
> 工作树：detached clean worktree `/private/tmp/aiscriptkill-mp0-baseline-bae4a55`
> 目的：记录 MP-0 修改前的真实单人能力，不代表多人功能已经实现。

## 1. 状态定义

```text
PASS      命令成功且覆盖目标能力
FAIL      命令执行完成但检查失败
SKIP      测试框架明确跳过
BLOCKED   外部运行条件不可用
NOT RUN   未执行
```

默认测试套件中的数据库探针被 skip，不等于真实 PostgreSQL lane 通过。

## 2. 环境

```text
Git SHA        bae4a55a6bd705455ee17ac65d9357dc7482dcbb
Git status     clean, detached HEAD
OS             macOS / Darwin arm64
Python         3.12.13
uv             0.11.19
Node           v26.3.0
npm            11.16.0
Supabase CLI   2.109.0
```

依赖通过以下锁文件驱动命令安装：

```bash
uv sync --frozen --extra dev
npm --prefix apps/web ci
```

结果：`PASS`。

npm 安装报告：

- React 19 与 `react-konva@18.2.16` 下 `react-reconciler` 的 peer warning。
- `npm audit` 报告 2 个 moderate vulnerabilities。
- `sharp`、`unrs-resolver` 的 install script 尚未列入 npm allowScripts。

这些是基线 warning，MP-0 不顺带升级前端依赖。

## 3. Pre-change 结果

| Lane | 命令 | 结果 | 细节 |
|---|---|---|---|
| Tools | `make verify-dev-tools` | PASS | pytest 9.1.1、Ruff 0.15.20、BasedPyright 1.39.9。 |
| Backend tests | `make test` | PASS / SKIP | 351 collected；349 passed，2 skipped；14.01s。 |
| Snow + RAG | 专项 pytest | PASS | 20 passed；2.25s。 |
| Ruff check | `ruff check engine` | PASS | `All checks passed!`。 |
| Ruff format | `ruff format --check engine` | FAIL | 基线已有 10 个文件需要格式化。 |
| BasedPyright | `make typecheck-api` | FAIL | 基线已有 10 个错误，均在 `runtime_action_mappers.py`。 |
| Web lint | `make lint-web` | PASS | ESLint 无错误。 |
| Web build | `CI=1 NEXT_PUBLIC_USE_MOCK=false npm ... build` | PASS | Next.js 15.5.20，全部路由构建成功。 |
| Local DB | `make db-start` | BLOCKED | Colima Docker socket 不可连接。 |
| DB privilege | `make test-database-privileges` | NOT RUN | `db-start` 阻断。 |
| SIGKILL recovery | `make test-checkpoint-recovery` | NOT RUN | `db-start` 阻断。 |

两个默认 suite skip 对应需要显式真实数据库 URL 的探针：

- database privilege probe
- checkpoint process recovery probe

## 4. 已知基线失败

### Ruff format

以下 10 个基线文件未通过当前 Ruff format check：

```text
engine/agents/npc_agent.py
engine/core/game_state_codec.py
engine/core/package_character_chapter_loader.py
engine/core/script_action_runtime.py
engine/repositories/runtime_package_repository.py
engine/repositories/session_mutations.py
engine/services/runtime_action_mappers.py
engine/tests/test_condition_evaluator.py
engine/tests/test_npc_agent.py
engine/tests/test_runtime_session_integration.py
```

MP-0 不应把这些既有格式问题伪报为本阶段引入；若为通过仓库 Gate 而统一格式化，必须单独记录机械变更。

### BasedPyright

基线的 10 个错误均位于：

```text
engine/services/runtime_action_mappers.py:232-249
```

主要涉及：

- `dict[str, object]` 不能传给 `JsonMapping`。
- requirement item/condition 的 unknown 或 partially unknown 类型。

这些错误在 MP-0 前已经存在。最终验证必须区分“新增错误为 0”和“全仓严格检查是否清零”。

## 5. Git 安全边界

固定 SHA worktree 在依赖安装和测试后仍为 clean。

主工作区另有用户已有删除项与未跟踪多人文档；本报告不把它们算作基线提交内容，
MP-0 也不得恢复或覆盖这些删除项。

## 6. Post-change 结果

执行位置：主工作区 `refactor/t1-t23-backend-stability`；结果包含 MP-0 变更以及工作区中
原有、未由 MP-0 修改的删除项。测试命令不会恢复或覆盖这些删除项。

| Lane | 命令 | 结果 | 细节 |
|---|---|---|---|
| Tools | `make verify-dev-tools` | PASS | pytest 9.1.1、Ruff 0.15.20、BasedPyright 1.39.9。 |
| MP-0 contracts | 4 个新增测试文件 | PASS | 24 passed；覆盖修正后的 15-command 联合、WS 方向/身份、完整 authoring、flags 和 fail-closed restore。 |
| Backend tests | `pytest engine/tests/ -q` | PASS / SKIP | 375 collected；373 passed，2 skipped；4.89s。 |
| Snow + RAG | 5 个专项测试文件 | PASS | 20 passed；2.59s。 |
| Ruff check | `ruff check engine` | PASS | `All checks passed!`。 |
| Changed format | MP-0 相关 Python 文件 | PASS | 20 files already formatted。 |
| Full format | `ruff format --check engine` | FAIL | 与基线相同的 10 个文件需要格式化；MP-0 文件无新增问题。 |
| Changed types | contracts + 变更生产文件 | PASS | 0 errors，0 warnings，0 notes。 |
| Full BasedPyright | `make typecheck-api` 等价命令 | FAIL | 与基线相同的 `runtime_action_mappers.py:232-249` 10 errors。 |
| Web lint | `make lint-web` 等价命令 | PASS | ESLint 无错误。 |
| Web build | live mode Next build | PASS | Next.js 15.5.20；全部路由构建成功。 |
| Contract imports | AST dependency probe | PASS | 未依赖 API/core/repository/service/LangGraph/FastAPI。 |
| Flags surface | flags 全部设为 true 后比较 routes | PASS | 路由集合不变；MP-0 未开放入口。 |
| Diff whitespace | `git diff --check` + cached check | PASS | 无 MP-0 diff whitespace error。 |
| MP-0 Markdown | fence、trailing whitespace、local links | PASS | 目标文档、ADR、报告、OpenWiki 通过。 |
| Local DB | `make db-start` | BLOCKED | 无法连接 `/Users/babiwei/.colima/default/docker.sock`。 |
| DB privilege | `make test-database-privileges` | NOT RUN | `db-start` 阻断。 |
| SIGKILL recovery | `make test-checkpoint-recovery` | NOT RUN | `db-start` 阻断。 |

### 6.1 回归结论

- 后端总测试从基线的 351 collected 增至 375 collected；24 个 MP-0 聚焦契约/flags/restore 测试全部通过。
- 两个 skip 仍是需要真实 PostgreSQL URL 的既有探针，不能解释为数据库通过。
- 全仓 Ruff format 与 BasedPyright 失败集合和 pre-change 基线一致；MP-0 变更文件单独检查通过。
- Snow Village 仍是 `max_players: 1` 的 `legacy_single` 回归包；专项 vertical slice 与 RAG 共 20 项通过。
- Multiplayer v1 已按主计划重新核对并修正：客户端 hello 只携 ticket/cursor，服务端 ready
  返回身份/revision/head；命令联合为 15 项；authoring 字段与主计划 YAML 一致。
- 三个 rollout flags 即使显式开启也不增加路由；多人 runtime、数据库和 UI 仍未开放。
- 合法 UUID 的公开 PATCH restore 固定返回 `409 SESSION_RESTORE_UNAVAILABLE`，且测试确认不访问 repository/DB。

### 6.2 文档检查边界

`docs/SCRIPT_PACKAGE_SCHEMA.md` 等历史长文档在未修改区域存在既有行尾空格；本阶段使用
`git diff --check` 保证没有新增 whitespace error，并对 MP-0 新建/重点修改文档执行 fence、
行尾和本地链接检查。没有为清理历史格式而制造大范围无关 diff。

## 7. MP-0 判定

```text
Offline contract/runtime gate   PASS
Legacy single-player regression PASS
Frontend lint/build             PASS
Real database lane              BLOCKED / NOT RUN
Multiplayer runtime             NOT IMPLEMENTED（符合 MP-0 范围）
```

MP-0 的“修正后契约基线与发布边界”完成；这不代表多人 runtime 已实现。真实数据库
privilege/recovery lane 保留为环境阻断，不得在后续发布说明中写成通过。
