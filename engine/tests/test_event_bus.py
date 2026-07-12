from dataclasses import replace

import pytest

from engine.core.event_bus import EventActionError, EventBus
from engine.core.package_schema import JsonMapping
from engine.tests.stategraph_fixtures import composite_event_package, initial_state


async def test_clue_discovery_trigger_evaluates_nested_all_and_any_condition() -> None:
    # 给定：已发现线索和对话次数满足嵌套的 all(any(...)) 触发器。
    package = composite_event_package()
    state = initial_state(package)
    state["unlocked_clues"].append("clue_1")
    state["discovered_clues"].append(
        {"clue_id": "clue_1", "round_id": "act1_round1", "scene_id": "main_hall", "is_key": False}
    )
    state["character_dialog_counts"]["npc"] = 2

    # 当：事件总线评估线索发现钩子。
    result = await EventBus(package).on_clue_discovered(state, "clue_1")

    # 则：已配置动作通过共享条件求值器触发。
    assert result["chat_history"][-1]["text"] == "复合条件命中"


async def test_clue_discovery_trigger_does_not_fire_when_nested_condition_is_false() -> None:
    # 给定：线索已发现，但嵌套 any 条件的两个分支均不为真。
    package = composite_event_package()
    state = initial_state(package)
    state["unlocked_clues"].append("clue_1")
    state["discovered_clues"].append(
        {"clue_id": "clue_1", "round_id": "act1_round1", "scene_id": "main_hall", "is_key": False}
    )
    state["character_dialog_counts"]["npc"] = 1

    # 当：评估同一个线索发现钩子。
    result = await EventBus(package).on_clue_discovered(state, "clue_1")

    # 则：不发出任何动作。
    assert result["chat_history"] == []


async def test_unknown_runtime_event_action_fails_with_typed_error() -> None:
    # 给定：无效动作绕过了导入时的剧本包校验器。
    package = composite_event_package()
    state = initial_state(package)
    sink = RecordingEventSink()

    # 当/则：运行时防御明确失败，而不是吞掉该动作。
    with pytest.raises(EventActionError) as captured:
        await EventBus(package, sink).process_actions(
            state,
            "runtime:defense",
            [{"action": "unknown_runtime_action"}],
        )
    assert getattr(captured.value, "code", None) == "EVENT_ACTION_UNSUPPORTED"
    assert sink.actions == []


async def test_completed_event_is_skipped_and_sink_receives_stable_idempotency_key() -> None:
    # 给定：同一个动作列表可能因检查点恢复而再次投递。
    package = composite_event_package()
    state = initial_state(package)
    sink = RecordingEventSink()
    event_bus = EventBus(package, sink)
    actions: list[JsonMapping] = [{"action": "dm_narrate", "text": "只应出现一次"}]

    # 当：先完成动作，再用返回状态重放同一个事件。
    first_result = await event_bus.process_actions(state, "stage:prologue:entry", actions)
    replayed_result = await event_bus.process_actions(
        first_result,
        "stage:prologue:entry",
        actions,
    )

    # 则：完成预检查阻止内存效果和外部效果重复，且幂等键跨重放保持稳定。
    assert [message["text"] for message in replayed_result["chat_history"]] == ["只应出现一次"]
    assert sink.actions == ["dm_narrate"]
    assert sink.idempotency_keys == [
        f"{state['session_id']}:stage:prologue:entry:0",
    ]


async def test_multiple_matching_clue_triggers_do_not_share_automatic_event_id() -> None:
    # 给定：同一线索声明两条都能命中的触发器，且每条动作下标都从零开始。
    package = composite_event_package()
    stage = package.stages[0]
    definition = dict(stage.definition)
    definition["on_clue_discovered"] = [
        {"condition": {"type": "always"}, "then": [{"action": "dm_narrate", "text": "一"}]},
        {"condition": {"type": "always"}, "then": [{"action": "dm_narrate", "text": "二"}]},
    ]
    package = replace(package, stages=(replace(stage, definition=definition),))
    state = initial_state(package)

    # 当：事件总线依次执行两条触发器。
    result = await EventBus(package).on_clue_discovered(state, "clue_1")

    # 则：触发器下标进入自动 ID，两条合法动作都不会被幂等预检查吞掉。
    assert [message["text"] for message in result["chat_history"]] == ["一", "二"]
    assert result["completed_events"] == [
        "stage:prologue:clue:clue_1:trigger:0:0",
        "stage:prologue:clue:clue_1:trigger:1:0",
    ]


class RecordingEventSink:
    def __init__(self) -> None:
        self.actions: list[str] = []
        self.idempotency_keys: list[str] = []

    async def execute(
        self,
        action: str,
        payload: JsonMapping,
        *,
        idempotency_key: str,
    ) -> None:
        _ = payload
        self.actions.append(action)
        self.idempotency_keys.append(idempotency_key)
