---
status: accepted
accepted: 2026-07-17
scope: MP-0 runtime safety
---

# LangGraph checkpoint 是唯一 continuation 恢复权威

## Context

当前系统同时保存完整 LangGraph `GameState` checkpoint 和有损的
`SessionRuntimeState` 查询投影。`session_checkpoints` 表又同时包含创建会话时的
`initial` projection row 与 versioned LangGraph envelope。旧 PATCH restore 只把指定行
解析成 projection 并更新 `game_sessions.state`，不会移动 LangGraph head；下一次动作仍会
恢复最新图 checkpoint，形成两条互相冲突的恢复路径。

此外，advisory lock、checkpoint commit 和 projection/chat/discovery commit 当前位于不同
事务，存在 checkpoint 已推进而投影写入失败的窗口。

## Decision

- 最新有效 LangGraph checkpoint 是动作 continuation 的唯一恢复权威。
- `game_sessions.state` 是 REST 查询投影；首次图动作前可作为 bootstrap，但不能独立 rewind。
- 已存在图 checkpoint 时，只允许现有 mapper 将 6 类单调外部进度合并回图状态：
  `unlocked_clues`、`discovered_evidences`、`viewed_evidences`、
  `unlocked_character_chapters`、`read_character_chapters`、
  `evidences_shown_to_npcs`。
- MP-0 暂停公开 PATCH restore：合法 UUID 稳定返回
  `409 SESSION_RESTORE_UNAVAILABLE`，不得读取或修改 repository。
- 完整 rewind 必须从指定 LangGraph checkpoint 创建新的 canonical head，再重新投影。

## Consequences

- 客户端不能再获得虚假的“恢复成功”响应。
- checkpoint/projection/command/event 同事务是后续多人写入的发布阻断项。
- 旧 repository restore 代码暂时保留但公开路径不可达，等待后续整体替换。

## Current storage matrix

| Storage | Current content | MP-0 authority |
|---|---|---|
| LangGraph envelope row | 完整图 continuation | 是 |
| `initial` checkpoint row | `SessionRuntimeState` projection | 仅 bootstrap |
| `game_sessions.state` | REST/query projection | 否 |
| chat/discoveries | 查询投影与外部单调进度 | 有限合并 |

## Scope

MP-0 不实现 checkpoint lineage、head relocation、请求幂等或统一事务；这些必须在多人
Command Service 上线前完成。
