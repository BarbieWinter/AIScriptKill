"""
GameState 定义
LangGraph StateGraph 的核心数据类型。
所有阶段共享此状态模型，通过加载不同剧本包配置驱动流程。
"""

from __future__ import annotations

from dataclasses import field
from typing import Any

from typing_extensions import TypedDict


class Message(TypedDict):
    """单条聊天消息"""
    id: str
    role: str  # "player" | "npc" | "dm"
    character_id: str | None
    text: str
    emotion: str | None
    timestamp: str


class GameEvent(TypedDict):
    """游戏事件：由条件触发或脚本配置触发"""
    event_id: str
    actions: list[dict[str, Any]]
    source: str  # "stage_entry" | "condition" | "player_action"


class GameState(TypedDict):
    """全局游戏状态（所有剧本共享 LangGraph 状态模型）"""
    # ── 会话信息 ──
    session_id: str
    script_id: str
    player_id: str

    # ── 流程控制 ──
    current_stage: str          # 如 "prologue" / "act1_investigation"
    previous_stage: str | None
    stage_entered_at: str       # ISO 8601 时间戳

    # ── 角色信息 ──
    player_character_id: str    # 玩家选择的角色 ID
    npc_states: dict[str, Any]  # {char_id: {trust_level, nervous, fear, ...}}

    # ── 解谜进度 ──
    unlocked_clues: list[str]       # 已解锁线索 ID 列表
    discovered_evidences: list[str]  # 已发现证物 ID 列表
    completed_events: list[str]      # 已完成事件 ID 列表

    # ── 对话上下文 ──
    chat_history: list[Message]
    pending_npc_responses: list[dict[str, Any]]

    # ── 条件缓存 ──
    condition_cache: dict[str, bool]

    # ── 事件队列 ──
    pending_events: list[GameEvent]

    # ── 结局状态 ──
    ending_triggered: bool
    ending_id: str | None
    final_submission: dict[str, Any] | None


def create_initial_state(
    session_id: str,
    script_id: str,
    player_id: str,
    player_character_id: str,
    entry_stage: str = "prologue",
) -> GameState:
    """创建初始 GameState

    引擎在创建新游戏会话时调用此函数。
    参数受运行时传入影响，不依赖特定剧本内容。
    """
    return GameState(
        session_id=session_id,
        script_id=script_id,
        player_id=player_id,
        current_stage=entry_stage,
        previous_stage=None,
        stage_entered_at="",
        player_character_id=player_character_id,
        npc_states={},
        unlocked_clues=[],
        discovered_evidences=[],
        completed_events=[],
        chat_history=[],
        pending_npc_responses=[],
        condition_cache={},
        pending_events=[],
        ending_triggered=False,
        ending_id=None,
        final_submission=None,
    )
