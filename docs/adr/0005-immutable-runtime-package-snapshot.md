---
status: accepted
accepted: 2026-07-18
implementation: partial
scope: MP-2 room creation and runtime package authority
---

# 房间创建时冻结不可变 runtime package snapshot

## Context

多人房间可能在创建后等待、跨天恢复，并在稍后才开始。`script_packages` 及其规范化子表会在同一
`script_id` 重新导入时被替换；package 的 version 字符串也不能证明内容没有变化。如果 lobby、选角
或 start 再读取 live package，重新发布可能在同一房间内改变角色、章节、阶段、结算规则或 DM 指引。

仅复制 version 不能锁定内容。仅在读取后比较规范化表也不能关闭
`PackageImportRepository._replace_structure()` 与房间快照之间的交错窗口。

## Decision

创建 `multiplayer_v1` 房间时，在同一个数据库事务中：

1. 以 `FOR SHARE` 锁定目标 published `script_packages` 主行。
2. 在锁仍由该事务持有时读取全部规范化 runtime records。
3. 校验 package 是首版支持的严格双人策略。
4. 编码 versioned snapshot，计算规范 SHA-256。
5. 将 snapshot、package version、digest 与房间、房主成员和 principal reservation 一起提交。

房间创建后的 lobby 角色列表、选角校验和 start 初始化只允许读取该 frozen snapshot，不再用
`script_id` 回读 live package。package version 是可读元数据，不是内容完整性证明；digest 才绑定
精确内容。

### Snapshot v1

`snapshot_schema_version` 当前为 `1`。JSON 对象包含且只包含：

- `package`：`id`、`title`、`version`、`status`、`config`；
- `stages`、`characters`、`chapters`、`clues`、`evidences`、`scenes`；
- `media_assets`、`endings`、`stage_index`、`dm_guide`。

列表记录逐字段镜像对应 runtime dataclass。`EndingRecord.on_trigger` 的 tuple 通过 JSON list 编码。
import-only 的 archive asset bytes 和 warnings 不进入快照；媒体引用仍包含在 `media_assets` 中。
解码后这两个排除字段恢复为空 tuple。

### Canonical bytes and digest

规范字节定义为：

```python
json.dumps(
    payload,
    ensure_ascii=False,
    allow_nan=False,
    sort_keys=True,
    separators=(",", ":"),
).encode("utf-8")
```

持久化 `runtime_package_sha256` 是上述字节的 lowercase SHA-256 hex。它是对 JSONB 逻辑值进行稳定
规范重编码后的摘要，不是 PostgreSQL 物理 JSONB 表示的摘要。

读取时必须：

- 要求 expected digest 匹配 `^[0-9a-f]{64}$`；
- 重新计算摘要并使用 constant-time comparison；
- 严格拒绝 missing/unknown fields、错误 primitive 类型、非字符串 mapping key、任意 tuple、
  non-finite float、未知 schema version、非法枚举、digest mismatch，以及可选的 package id/version
  pin mismatch；
- 重建冻结 runtime record，并为任意 JSON mapping 做 defensive copy。

### Transaction boundary

`get_runtime_package(..., lock_existing=True)` 已提供 PostgreSQL `FOR SHARE` 读取原语。该锁只有在调用
方继续持有同一个事务时才有效；先读取后释放事务、再创建房间不满足本 ADR。

Room create service 已在同一 injected `AsyncSession` 中接线：持有 package `FOR SHARE` 读取、编码
snapshot/digest、写 room/host/reservation，并在成功路径最终 commit 一次。该路径已通过 focused 与 full
engine tests；但真实 PostgreSQL republish/locking lane 仍未运行，所以不能宣称数据库交错 gate 已关闭。

## Consequences

- 同一 `script_id` 即使以相同 version 字符串重新发布，旧房间仍可使用创建时的角色、阶段、章节、
  规则和 digest。
- 每个房间会复制一份完整 runtime JSON，增加存储成本；这是可恢复性和防止内容漂移的有意取舍。
- snapshot 包含服务端私密内容，绝不能通过 lobby snapshot、错误详情或浏览器日志返回；HTTP 只返回
  participant-safe package summary 和 lobby projection。
- digest 或结构校验失败时必须 fail closed，不能静默回退到 live package。
- schema 演进必须增加 snapshot schema version 和显式 decoder/upgrader，不能就地改变旧房间语义。

## Alternatives rejected

- **只存 package version**：version 可以被误用或重复，不能证明内容相同。
- **每次从规范化 live tables 重建**：重新发布会改变未完成房间，且读取期间存在交错窗口。
- **复制部分角色/阶段字段**：会漏掉章节、材料、结算或 DM 指引，无法初始化精确 `GameStateV2`。
- **摘要 PostgreSQL 物理 JSONB bytes**：数据库内部表示不是跨实现、跨序列化器的稳定 wire contract。

## Verification status

Codec、严格 decode、policy/stage validation、`FOR SHARE` SQL 形态和 create service 接线已有 focused/full
engine evidence。真实 PostgreSQL migration/locking/republish lane 仍为 `BLOCKED / NOT RUN`，因此本 ADR
的设计已接受、应用层实现已接线，但数据库并发证明仍为 partial。未 commit、未 push。
