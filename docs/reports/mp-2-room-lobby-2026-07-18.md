# MP-2 房间大厅阶段验证报告

> 日期：2026-07-18
> 开发分支：`feature/mp-2-room-lobby`
> 集成目标：`/private/tmp/aiscriptkill-mp1-offline-state-machine`
> 提交状态：未 commit、未 push
> 判定时点：MP-2 后端、前端与静态验证已完成；真实 PostgreSQL 和 live-stack 浏览器验证受环境阻塞

## 1. 判定

```text
MP-2 persistence/schema primitives       IMPLEMENTED / FOCUSED PASS
Immutable runtime package codec/lock     IMPLEMENTED / FOCUSED PASS
Anonymous auth + HTTP schemas            IMPLEMENTED / FOCUSED PASS
HTTP lobby backend end-to-end            IMPLEMENTED / STATIC+UNIT PASS
Frontend lobby routes                    IMPLEMENTED / STATIC PASS
Mocked-contract Playwright               PASS (1 test; NOT live E2E)
Live-stack test definition/source       IMPLEMENTED / STATIC PASS
Real PostgreSQL migration/concurrency     BLOCKED / NOT RUN
Live-stack multi-context Playwright       BLOCKED / NOT RUN
MP-2 release readiness                    NOT READY
```

MP-2 仍不能标记为 COMPLETE 或 release-ready。当前已集成 persistence、snapshot、auth/schema、完整
HTTP lobby backend 和前端大厅，并通过 focused/full backend regression、Python lint/types、前端静态检查与
mocked-contract Playwright。真实 PostgreSQL 与真实后端/Supabase 浏览器闭环没有运行。下面的 PASS 只适用于
明确列出的 focused/static/unit 或 mocked-contract 范围。

## 2. 已集成范围

### Persistence and database boundary

- `game_sessions` 增加 mode-aware multiplayer columns、revision/event head、GameStateV2 schema version、
  pinned package version/snapshot/SHA，以及 started/closed timestamps；旧 `legacy_single` 行保留原状态和
  非空 `player_character_id` 约束。
- 新增 `room_members`、`room_character_assignments`、`room_invites`、
  `room_required_members`、`room_principal_reservations`。
- 数据库唯一键/组合 FK 建模一房一 principal、一 joined host、同房角色唯一、start 后 canonical
  required-member 集合，以及 principal 与 member identity 一致性。
- 五张新表启用 RLS，只定义 `service_role_full_access`；migration 撤销 `anon`/`authenticated` 权限。
- SQLAlchemy metadata、`REQUIRED_PUBLIC_TABLES` 和 privilege probe inventory 已同步。

这些约束已通过结构/metadata 测试，但尚未在 disposable PostgreSQL 上应用 migration 并实际探测。

### Immutable runtime package snapshot

- Snapshot schema v1 冻结 package/config、完整 runtime records、stage index 和 DM guide；排除 importer-only
  asset bytes 与 warnings。
- 稳定 sorted-key compact UTF-8 JSON 生成 lowercase SHA-256；decode 严格验证结构、类型、枚举、schema
  version、digest 及可选 package id/version pin。
- `get_runtime_package(..., lock_existing=True)` 可生成 PostgreSQL `FOR SHARE`，用于阻止 package 主行在
  child rows 读取期间被替换。

Codec、锁原语及 room create/start 的 frozen-snapshot 接线已实现，并通过 focused unit/service evidence。
但真实 PostgreSQL republish/locking lane 仍未运行，因此内容锁定的数据库并发保证保持环境阻塞状态。

### Identity, schemas, and frontend

- 专用 anonymous principal 依赖要求合法 Supabase bearer JWT、UUID `sub` 和
  `is_anonymous=true`；legacy optional auth 行为保持独立。
- Strict create/invite/lobby/command schemas 不接受客户端提交 principal/member actor。
- `/multiplayer`、`/invite/[token]`、`/play/[sessionId]/lobby` 前端路由已集成。
- React Query 仅在 lobby 每 2 秒 HTTP polling；active 停止 polling，只显示 MP-6 placeholder。
- invite 成功后使用 `router.replace()` 清除活动 URL 中的 token；大厅不使用 legacy gameplay store，
  也不创建 application WebSocket。

## 3. 验证证据

| Lane | 范围/命令 | 结果 | 说明 |
|---|---|---|---|
| Groundwork/auth/contracts | integrated focused selection | PASS | 32 passed。 |
| Persistence + snapshot | integrated focused selection | PASS / SKIP | 48 passed，1 skipped；skip 是真实 PostgreSQL lane，不能算 PASS。 |
| Backend regression before room backend landed | `uv --directory /private/tmp/aiscriptkill-mp1-offline-state-machine run --frozen pytest engine/tests -q` | PASS / SKIP | 430 passed，2 skipped；5.55s。该 count 在 room service tests 加入前产生，不能替代最终回归，两个 skip 也不是 PostgreSQL PASS。 |
| Room backend focused | exact target-qualified command below | PASS / SKIP | 38 passed，1 skipped；0.80s。skip 是真实 PostgreSQL/Docker lane。 |
| Room backend-specific | exact target-qualified command below | PASS | 7 passed；0.49s。 |
| Final backend regression | exact target-qualified command below | PASS / SKIP | 442 passed，2 skipped；5.11s。该结果 supersede 早期 430/2 和 pre-final rerun；两个 skip 均不得当作 PostgreSQL PASS。 |
| Python lint/types | exact target-qualified commands below | PASS | Ruff check 为 `All checks passed!`；focused production BasedPyright 为 0 errors、0 warnings、0 notes。两项 duration 未记录，不推断。 |
| App/OpenAPI build | exact target-qualified commands below | PASS | app import/build 输出 `app-ok 11`；OpenAPI inventory 包含全部 legacy 与 7 个 MP-2 session routes。duration 未记录。 |
| Web lint | `npm --prefix apps/web run lint` | PASS | 前端 agent 实际运行。 |
| Web typecheck | `npx --prefix apps/web tsc --noEmit -p apps/web/tsconfig.json` | PASS | 前端 agent 独立实际运行；不采用曾只打印 help 的错误 `npm exec` 尝试。 |
| Web production build | 带 public Supabase placeholders 的 `npm --prefix apps/web run build` | PASS | serial rerun 通过，并包含 `/multiplayer`、`/invite/[token]`、`/play/[sessionId]/lobby`；曾与 Playwright 并发写同一 `.next` 而出现 `/_document` artifact collision，不计作 serial 功能失败。 |
| Browser contract test | `npm --prefix apps/web run test:e2e` | PASS | 当前隔离端口 serial rerun 为 7 passed（其中 1 个 MP-2 lobby、6 个 MP-3 recovery）；HTTP 与 Supabase auth 均在浏览器层 mock。 |
| Live browser definition | `npm --prefix apps/web run test:e2e:mp2-live -- --list` | STATIC PASS | 独立 config 只发现 1 个 `mp2-live-chromium` test；该 spec 使用两个独立 context，不拦截 Auth/API，且 readiness/package 缺失会以 `MP-2 LIVE BLOCKED` 失败。此结果只证明 test definition 可加载，不证明 live flow 已运行。 |
| Production dependency audit | `npm audit --omit=dev` | ADVISORY | exit 1；Next dependency chain 中 `postcss < 8.5.10` 有 2 个 moderate vulnerabilities，GHSA-qx2v-qp2m-jg93。 |
| Real PostgreSQL | migration/constraints/concurrency/privileges/republish | BLOCKED / NOT RUN | Docker/Colima daemon 不可用；没有 disposable PostgreSQL 证据。 |
| Live-stack Playwright | real Supabase Auth + real FastAPI + real PostgreSQL | BLOCKED / NOT RUN | mocked-contract Playwright 不能替代该 lane；本地 Docker/Supabase 数据层不可用。 |
| FastAPI route inventory | OpenAPI paths + static-before-dynamic order assertion | PASS | 7 个 MP-2 HTTP endpoints 均已注册，`/sessions/current` 位于 `/{session_id}` 前；final API recheck 为 42 passed，0.87s。 |
| Repository transaction boundary | source/test contract | PASS | room repository 无 `commit()`/`SessionFactory`；成功 mutation 由 service 最终 commit。 |
| Final diff whitespace | `git diff --check` | PASS | 完整累积 diff 无 whitespace error。 |
| Documentation diff whitespace | `git diff --check -- README.md docs openwiki` | PASS | 已跟踪文档 diff 无 whitespace error；untracked 新文档由下一行自定义检查覆盖。 |
| Markdown fences/whitespace | Python 读取本次 9 个 Markdown 文件 | PASS | 检查 triple-backtick parity、trailing whitespace 和 tab。 |
| Local Markdown links | Python 解析本次 9 个 Markdown 文件的相对链接 | PASS | 所有相对文件 target 存在。 |

### 3.1 Backend exact provenance

由于验证 agent 的工作目录是另一个 worktree，backend 命令使用 `PYTHONSAFEPATH=1` 和目标绝对
`PYTHONPATH`，避免错误导入其他 checkout。实际命令如下：

```bash
PYTHONSAFEPATH=1 PYTHONPATH=/private/tmp/aiscriptkill-mp1-offline-state-machine /private/tmp/aiscriptkill-mp1-offline-state-machine/.venv/bin/python -m pytest /private/tmp/aiscriptkill-mp1-offline-state-machine/engine/tests/test_multiplayer_room_backend.py -q

PYTHONSAFEPATH=1 PYTHONPATH=/private/tmp/aiscriptkill-mp1-offline-state-machine /private/tmp/aiscriptkill-mp1-offline-state-machine/.venv/bin/python -m pytest /private/tmp/aiscriptkill-mp1-offline-state-machine/engine/tests/test_multiplayer_room_backend.py /private/tmp/aiscriptkill-mp1-offline-state-machine/engine/tests/test_multiplayer_room_contracts.py /private/tmp/aiscriptkill-mp1-offline-state-machine/engine/tests/test_runtime_package_snapshot.py /private/tmp/aiscriptkill-mp1-offline-state-machine/engine/tests/test_multiplayer_room_migration.py /private/tmp/aiscriptkill-mp1-offline-state-machine/engine/tests/test_database_access_boundary.py -q

PYTHONSAFEPATH=1 PYTHONPATH=/private/tmp/aiscriptkill-mp1-offline-state-machine /private/tmp/aiscriptkill-mp1-offline-state-machine/.venv/bin/python -m pytest /private/tmp/aiscriptkill-mp1-offline-state-machine/engine/tests -q

/private/tmp/aiscriptkill-mp1-offline-state-machine/.venv/bin/ruff check /private/tmp/aiscriptkill-mp1-offline-state-machine/engine/repositories/multiplayer_room_models.py /private/tmp/aiscriptkill-mp1-offline-state-machine/engine/repositories/multiplayer_room_repository.py /private/tmp/aiscriptkill-mp1-offline-state-machine/engine/services/multiplayer_feature.py /private/tmp/aiscriptkill-mp1-offline-state-machine/engine/services/multiplayer_room_service.py /private/tmp/aiscriptkill-mp1-offline-state-machine/engine/api/schemas/multiplayer_rooms.py /private/tmp/aiscriptkill-mp1-offline-state-machine/engine/api/middleware/auth.py /private/tmp/aiscriptkill-mp1-offline-state-machine/engine/api/routes/sessions.py /private/tmp/aiscriptkill-mp1-offline-state-machine/engine/api/main.py /private/tmp/aiscriptkill-mp1-offline-state-machine/engine/tests/test_multiplayer_room_backend.py

PYTHONSAFEPATH=1 PYTHONPATH=/private/tmp/aiscriptkill-mp1-offline-state-machine /private/tmp/aiscriptkill-mp1-offline-state-machine/.venv/bin/basedpyright --project /private/tmp/aiscriptkill-mp1-offline-state-machine/pyproject.toml /private/tmp/aiscriptkill-mp1-offline-state-machine/engine/repositories/multiplayer_room_models.py /private/tmp/aiscriptkill-mp1-offline-state-machine/engine/repositories/multiplayer_room_repository.py /private/tmp/aiscriptkill-mp1-offline-state-machine/engine/services/multiplayer_feature.py /private/tmp/aiscriptkill-mp1-offline-state-machine/engine/services/multiplayer_room_service.py /private/tmp/aiscriptkill-mp1-offline-state-machine/engine/api/schemas/multiplayer_rooms.py /private/tmp/aiscriptkill-mp1-offline-state-machine/engine/api/middleware/auth.py /private/tmp/aiscriptkill-mp1-offline-state-machine/engine/api/routes/sessions.py /private/tmp/aiscriptkill-mp1-offline-state-machine/engine/api/main.py

PYTHONSAFEPATH=1 PYTHONPATH=/private/tmp/aiscriptkill-mp1-offline-state-machine /private/tmp/aiscriptkill-mp1-offline-state-machine/.venv/bin/python -c 'from engine.api.main import create_app; app=create_app(); print("app-ok", len(app.routes))'

PYTHONSAFEPATH=1 PYTHONPATH=/private/tmp/aiscriptkill-mp1-offline-state-machine /private/tmp/aiscriptkill-mp1-offline-state-machine/.venv/bin/python -m pytest /private/tmp/aiscriptkill-mp1-offline-state-machine/engine/tests/test_multiplayer_room_backend.py /private/tmp/aiscriptkill-mp1-offline-state-machine/engine/tests/test_api_contracts.py -q
```

OpenAPI inventory 使用同一目标解释器执行：

```bash
PYTHONSAFEPATH=1 PYTHONPATH=/private/tmp/aiscriptkill-mp1-offline-state-machine /private/tmp/aiscriptkill-mp1-offline-state-machine/.venv/bin/python - <<'PY'
from engine.api.main import create_app
schema=create_app().openapi()
for path in schema['paths']:
    if 'session' in path:
        print(path, sorted(schema['paths'][path]))
PY
```

`npm audit --omit=dev` 的两项 moderate advisory 是已知未解决依赖问题，不是功能测试失败。建议的
`--force` resolution 会安装 breaking Next version，因此本阶段没有自动应用；也不得宣称零漏洞。

前端 mocked-contract Playwright 使用三个独立 browser contexts，并覆盖 create、两次 invite、copy、revoke、
revoked-token rejection、accept 后 token-removing redirect、anonymous session reload、select/unselect、
ready/unready、distinct assignment、start、active placeholder 与无 application WebSocket。它证明 UI 对已定义
HTTP contract 的行为，不证明真实 JWT、数据库事务、RLS、并发或 live backend 集成。

独立的 `playwright.live.config.ts` 和 `multiplayer-lobby.live.spec.ts` 已加入：它们不会启动 fallback dev server，
不会 route/mock Supabase Auth 或 `/api/v1/**`，并先检查 FastAPI database health 与已发布
`mp1-two-player` inventory。两个真实 browser contexts 随后执行 create/invite/accept、选角、ready、换角清
ready、start 和 MP-6 placeholder 断言。该 lane 目前只通过 lint/typecheck/test discovery；由于真实栈未运行，
不能记为 live PASS。

## 4. 尚未关闭的 MP-2 Gate

- [ ] migration 在含代表性 legacy rows 的真实 PostgreSQL 上成功应用。
- [ ] 同 principal 并发 create 只有一个 reservation。
- [ ] 不同 invite 并发 accept 不超容量，第三人稳定得到 `ROOM_FULL`。
- [ ] 并发抢同角色只有一个 winner。
- [ ] start 仅一次、canonical required-member 顺序稳定，失败不留 partial state。
- [ ] expired/revoked/exhausted/full invite 在真实数据库事务下验证。
- [ ] outsider UUID 不能读写；身份丢失后新 anonymous JWT 不能认领旧 membership。
- [ ] 创建房间后 republish 不改变 lobby、digest 或 start state。
- [ ] `anon`/`authenticated` 对五张新表无 effective privileges。
- [ ] 两个真实 browser contexts 通过 live Supabase/FastAPI/PostgreSQL lobby 流程。
- [x] 后端 repository/service/routes 完成，并通过 focused、full regression、Ruff、BasedPyright 与 OpenAPI build。
  独立 subagent review 因隔离目录读取权限受限而未执行，不能声称 independent review PASS。

## 5. 范围外

MP-2 不实现 persistent command replay/idempotency、checkpoint 与 event/outbox 同事务、stage commands、durable
chat、gameplay participant snapshot、认证 WebSocket/replay/presence、完整 post-start gameplay 或 AI DM。
`active` 页面只显示明确的 MP-6 placeholder。

## 6. 发布判定

在第 4 节全部 required gate 通过并把命令、counts 和环境记录补回本报告前，MP-2 保持
`IN PROGRESS / NOT RELEASE-READY`。本次文档更新没有 commit，也没有 push。
