import pytest
from langgraph.checkpoint.memory import InMemorySaver

from engine.api.schemas.common import ActionType
from engine.core.script_engine import ScriptEngine
from engine.core.script_engine_errors import ScriptEngineActionError
from engine.tests.stategraph_fixtures import (
    ManualClock,
    action_package,
    elapsed_time_package,
    initial_state,
)


@pytest.mark.parametrize(
    ("action_id", "target"),
    [
        ("talk_to_npc", "npc"),
        ("examine_scene", "main_hall"),
        ("show_evidence", "knife:npc"),
        ("use_card", "insight"),
        ("open_clue_board", None),
        ("request_advance", None),
    ],
)
async def test_each_enabled_action_accepts_its_core_target_contract(
    action_id: ActionType,
    target: str | None,
) -> None:
    # 给定：所有玩法动作均已启用，且证物已经发现。
    package = action_package()
    engine = ScriptEngine.from_package(package)
    state = initial_state(package)
    state["discovered_evidences"].append("knife")

    # 当：使用对其动作类型有效的目标执行动作。
    result = await engine.run_action(state, action_id=action_id, target=target, text="你好")

    # 则：记录动作并应用其确定性核心效果。
    assert result["performed_actions"][-1] == {"action_id": action_id, "target": target}
    match action_id:
        case "talk_to_npc":
            assert result["character_dialog_counts"] == {"npc": 1}
            assert result["chat_history"][-1]["character_id"] == "npc"
        case "examine_scene":
            assert result["current_scene"] == "main_hall"
        case "show_evidence":
            assert result["evidences_shown_to_npcs"] == [
                {"evidence_id": "knife", "character_id": "npc"},
            ]
        case "use_card":
            assert result["used_cards"] == [{"card_id": "insight", "card_type": None}]
        case "open_clue_board":
            assert result["player_requests"] == []
        case "request_advance":
            assert result["player_requests"] == ["request_advance"]


@pytest.mark.parametrize(
    ("action_id", "target", "expected_code"),
    [
        ("talk_to_npc", None, "ACTION_TARGET_REQUIRED"),
        ("talk_to_npc", "missing", "ACTION_TARGET_UNAVAILABLE"),
        ("examine_scene", None, "ACTION_TARGET_REQUIRED"),
        ("examine_scene", "missing", "ACTION_TARGET_UNAVAILABLE"),
        ("show_evidence", "knife", "ACTION_TARGET_INVALID"),
        ("show_evidence", "missing:npc", "EVIDENCE_NOT_DISCOVERED"),
        ("show_evidence", "knife:missing", "ACTION_TARGET_UNAVAILABLE"),
        ("use_card", "", "ACTION_TARGET_REQUIRED"),
        ("open_clue_board", "unexpected", "ACTION_TARGET_INVALID"),
    ],
)
async def test_invalid_action_targets_fail_with_typed_codes(
    action_id: ActionType,
    target: str | None,
    expected_code: str,
) -> None:
    # 给定：已启用动作收到格式错误或不可用的目标。
    package = action_package()
    engine = ScriptEngine.from_package(package)
    state = initial_state(package)
    state["discovered_evidences"].append("knife")

    # 当/则：核心拒绝动作，而不是静默记录空操作。
    with pytest.raises(ScriptEngineActionError) as captured:
        await engine.run_action(state, action_id=action_id, target=target)
    assert getattr(captured.value, "code", None) == expected_code


async def test_empty_available_actions_does_not_enable_every_action() -> None:
    # 给定：当前阶段明确不启用任何玩法动作。
    package = action_package()
    package.stages[0].definition["available_actions"] = []
    engine = ScriptEngine.from_package(package)
    state = initial_state(package)

    # 当/则：动作以类型化可用性错误失败。
    with pytest.raises(ScriptEngineActionError) as captured:
        await engine.run_action(state, action_id="open_clue_board")
    assert getattr(captured.value, "code", None) == "ACTION_NOT_AVAILABLE"


async def test_rejected_action_does_not_replace_the_last_valid_checkpoint() -> None:
    # 给定：一个有效回合已经生成可恢复的检查点。
    package = action_package()
    checkpointer = InMemorySaver()
    engine = ScriptEngine.from_package(package, checkpointer=checkpointer)
    state = initial_state(package)
    state = await engine.run_action(state, action_id="open_clue_board")

    # 当：下一动作以当前阶段不可用的角色为目标。
    with pytest.raises(ScriptEngineActionError):
        await engine.run_action(state, action_id="talk_to_npc", target="missing")
    restored = await engine.restore_state(thread_id=state["session_id"])

    # 则：恢复返回最后一个成功回合，绝不返回被拒绝的待处理输入。
    assert restored is not None
    assert restored["pending_action"] is None
    assert restored["performed_actions"] == [
        {"action_id": "open_clue_board", "target": None},
    ]


async def test_each_turn_advances_time_and_stage_entry_resets_elapsed_origin() -> None:
    # 给定：阶段在经过五分钟后退出，并使用手动控制的时钟。
    package = elapsed_time_package()
    clock = ManualClock("2026-07-11T00:00:00+00:00")
    engine = ScriptEngine.from_package(package, clock=clock)
    state = initial_state(package)

    # 当：动作分别发生在五分钟阈值前后。
    state = await engine.run_action(state, action_id="open_clue_board")
    assert state["current_stage"] == "prologue"
    assert state["stage_entered_at"] == "2026-07-11T00:00:00+00:00"
    clock.set("2026-07-11T00:04:00+00:00")
    state = await engine.run_action(state, action_id="open_clue_board")
    assert state["current_stage"] == "prologue"
    assert state["current_time"] == "2026-07-11T00:04:00+00:00"
    clock.set("2026-07-11T00:06:00+00:00")
    state = await engine.run_action(state, action_id="open_clue_board")

    # 则：条件变为真，下一阶段以本回合时间戳开始。
    assert state["current_stage"] == "act1"
    assert state["current_time"] == "2026-07-11T00:06:00+00:00"
    assert state["stage_entered_at"] == "2026-07-11T00:06:00+00:00"


async def test_dm_and_npc_messages_use_the_injected_clock() -> None:
    # 给定：确定性时钟，以及阶段进入旁白之后的 NPC 对话。
    package = action_package()
    clock = ManualClock("2026-07-11T08:30:00+00:00")
    engine = ScriptEngine.from_package(package, clock=clock)
    state = initial_state(package)

    # 当：第一回合进入阶段并与 NPC 对话。
    state = await engine.run_action(state, action_id="talk_to_npc", target="npc", text="你好")

    # 则：两条核心生成的消息使用相同的确定性时间源。
    assert [message["timestamp"] for message in state["chat_history"]] == [
        "2026-07-11T08:30:00+00:00",
        "2026-07-11T08:30:00+00:00",
    ]
