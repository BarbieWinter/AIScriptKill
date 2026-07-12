from uuid import uuid4

from langgraph.checkpoint.memory import InMemorySaver

from engine.core.checkpoint import SupabaseSessionCheckpointSaver
from engine.core.game_state import create_initial_state
from engine.core.package_loader import load_package_archive
from engine.core.package_schema import JsonMapping
from engine.core.script_engine import ScriptEngine
from engine.tests.checkpoint_fakes import MemoryCheckpointSession
from engine.tests.package_loader_fixtures import package_archive
from engine.tests.stategraph_fixtures import state_graph_package, state_graph_package_files


async def test_script_engine_runs_stage_transition_and_ending_with_event_sequence() -> None:
    # 给定：序章进入事件会解锁内容、玩家动作会退出阶段的剧本包。
    package = state_graph_package()
    event_sink = RecordingEventSink()
    engine = ScriptEngine.from_package(package, event_sink=event_sink)
    state = create_initial_state(
        session_id=str(uuid4()),
        script_id=package.package.id,
        player_id=str(uuid4()),
        player_character_id="player",
        entry_stage="prologue",
    )

    # 当：玩家请求 DM 推进并离开序章。
    state = await engine.run_action(state, action_id="request_advance", target="request_advance")

    # 则：图执行进入事件、动作处理、条件检查和阶段进入。
    assert state["current_stage"] == "act1"
    assert state["previous_stage"] == "prologue"
    assert "prologue" in state["completed_stages"]
    assert "clue_1" in state["unlocked_clues"]
    assert event_sink.actions == [
        "dm_narrate",
        "play_audio",
        "unlock_clue_round",
        "play_audio",
        "save_checkpoint",
        "dm_narrate",
    ]

    # 当：玩家在第一幕提交正确的最终答案。
    state["final_submission"] = {
        "suspect": "npc",
        "key_evidences": ["knife"],
    }
    state["answer_key"] = {"suspect": "npc"}
    state = await engine.run_action(state, action_id="request_advance", target="finish")

    # 则：结局条件触发，且结局动作仅执行一次。
    assert state["ending_triggered"] is True
    assert state["ending_id"] == "truth"
    assert event_sink.actions[-2:] == ["dm_narrate", "play_audio"]


async def test_script_engine_restores_state_from_langgraph_checkpoint() -> None:
    # 给定：带有 LangGraph 检查点保存器且已完成一个动作的编译图。
    package = state_graph_package()
    checkpointer = InMemorySaver()
    session_id = str(uuid4())
    engine = ScriptEngine.from_package(package, checkpointer=checkpointer)
    state = create_initial_state(
        session_id=session_id,
        script_id=package.package.id,
        player_id=str(uuid4()),
        player_character_id="player",
        entry_stage="prologue",
    )
    await engine.run_action(
        state,
        action_id="request_advance",
        target="request_advance",
        thread_id=session_id,
    )

    # 当：进程重启后，使用同一检查点保存器创建新的引擎实例。
    restarted_engine = ScriptEngine.from_package(package, checkpointer=checkpointer)
    restored_state = await restarted_engine.restore_state(thread_id=session_id)

    # 则：最新检查点重建完整的 GameState。
    assert restored_state is not None
    assert restored_state["current_stage"] == "act1"
    assert restored_state["previous_stage"] == "prologue"
    assert restored_state["unlocked_clues"] == ["clue_1", "clue_2", "clue_3", "clue_4"]


async def test_script_engine_restores_state_from_session_checkpoints_after_restart() -> None:
    # 给定：将 LangGraph 检查点持久化到 session_checkpoints 的 Supabase 保存器。
    package = state_graph_package()
    session = MemoryCheckpointSession()
    session_id = str(uuid4())
    engine = ScriptEngine.from_package(
        package,
        checkpointer=SupabaseSessionCheckpointSaver(session),
    )
    state = create_initial_state(
        session_id=session_id,
        script_id=package.package.id,
        player_id=str(uuid4()),
        player_character_id="player",
        entry_stage="prologue",
    )
    await engine.run_action(
        state,
        action_id="request_advance",
        target="request_advance",
        thread_id=session_id,
    )

    # 当：原进程结束后，新引擎使用同一个检查点表。
    restarted_engine = ScriptEngine.from_package(
        package,
        checkpointer=SupabaseSessionCheckpointSaver(session),
    )
    restored_state = await restarted_engine.restore_state(thread_id=session_id)

    # 则：持久化的会话检查点足以从推进后的阶段继续运行。
    assert restored_state is not None
    assert restored_state["current_stage"] == "act1"
    assert restored_state["previous_stage"] == "prologue"
    assert len(session.rows) > 0


async def test_script_engine_rejects_stage_jump_without_stage_permission() -> None:
    # 给定：阶段进入事件尝试从序章直接跳到复盘阶段。
    files = state_graph_package_files()
    prologue_file = files["stages/prologue.yml"]
    if not isinstance(prologue_file, str):
        raise AssertionError("prologue stage fixture must be text")
    transition_event = "\n".join(
        [
            '  - action: "play_audio"',
            '    asset_id: "intro"',
            '  - action: "transition_to"',
            '    stage_id: "review"',
        ],
    )
    files["stages/prologue.yml"] = prologue_file.replace(
        '  - action: "play_audio"\n    asset_id: "intro"',
        transition_event,
    )
    package = load_package_archive(package_archive(files))
    engine = ScriptEngine.from_package(package)
    state = create_initial_state(
        session_id=str(uuid4()),
        script_id=package.package.id,
        player_id=str(uuid4()),
        player_character_id="player",
        entry_stage="prologue",
    )

    # 当：图执行序章进入和玩家动作。
    state = await engine.run_action(state, action_id="open_clue_board")

    # 则：记录非法跳转，但阶段不会越级推进。
    assert state["current_stage"] == "prologue"
    assert state["blocked_transitions"] == [
        {"from_stage": "prologue", "to_stage": "review", "reason": "stage_jump_denied"},
    ]


async def test_script_engine_blocks_transition_when_target_entry_condition_is_false() -> None:
    # 给定：顺序中的下一阶段存在未满足的进入条件。
    files = state_graph_package_files()
    act1 = files["stages/act1.yml"]
    assert isinstance(act1, str)
    files["stages/act1.yml"] = act1.replace(
        "entry_conditions: []",
        "entry_conditions:\n  - type: never",
    )
    package = load_package_archive(package_archive(files))
    engine = ScriptEngine.from_package(package)
    state = create_initial_state(
        session_id=str(uuid4()),
        script_id=package.package.id,
        player_id=str(uuid4()),
        player_character_id="player",
        entry_stage="prologue",
    )

    # 当：当前阶段的退出条件请求正常推进。
    state = await engine.run_action(state, action_id="request_advance")

    # 则：当前阶段保持活动状态，并记录进入守卫失败。
    assert state["current_stage"] == "prologue"
    assert state["completed_stages"] == []
    assert state["blocked_transitions"][-1] == {
        "from_stage": "prologue",
        "to_stage": "act1",
        "reason": "entry_conditions_not_met",
    }


async def test_target_entry_condition_observes_the_stage_being_completed() -> None:
    # 给定：下一阶段要求当前阶段完成后才能进入。
    files = state_graph_package_files()
    act1 = files["stages/act1.yml"]
    assert isinstance(act1, str)
    files["stages/act1.yml"] = act1.replace(
        "entry_conditions: []",
        'entry_conditions:\n  - type: stage_completed\n    stage_id: "prologue"',
    )
    package = load_package_archive(package_archive(files))
    engine = ScriptEngine.from_package(package)
    state = create_initial_state(
        session_id=str(uuid4()),
        script_id=package.package.id,
        player_id=str(uuid4()),
        player_character_id="player",
        entry_stage="prologue",
    )

    # 当：当前阶段满足退出条件。
    state = await engine.run_action(state, action_id="request_advance")

    # 则：预期完成状态满足目标守卫并被提交。
    assert state["current_stage"] == "act1"
    assert state["completed_stages"] == ["prologue"]
    assert state["blocked_transitions"] == []


async def test_script_engine_allows_configured_forward_jump() -> None:
    # 给定：阶段明确允许向前跳转到非相邻阶段。
    files = state_graph_package_files()
    prologue = files["stages/prologue.yml"]
    assert isinstance(prologue, str)
    files["stages/prologue.yml"] = prologue.replace(
        'id: "prologue"',
        'id: "prologue"\nallow_stage_jump: true',
    ).replace(
        '  - action: "play_audio"\n    asset_id: "intro"',
        '  - action: "play_audio"\n    asset_id: "intro"\n'
        '  - action: "transition_to"\n    stage_id: "review"',
    )
    package = load_package_archive(package_archive(files))
    engine = ScriptEngine.from_package(package)
    state = create_initial_state(
        session_id=str(uuid4()),
        script_id=package.package.id,
        player_id=str(uuid4()),
        player_character_id="player",
        entry_stage="prologue",
    )

    # 当：进入事件请求已配置的跳转。
    state = await engine.run_action(state, action_id="open_clue_board")

    # 则：图到达非相邻目标，而不是阻止跳转。
    assert state["current_stage"] == "review"


async def test_script_engine_allows_configured_stage_regression() -> None:
    # 给定：第一幕明确允许回退，并在进入时请求上一阶段。
    files = state_graph_package_files()
    act1 = files["stages/act1.yml"]
    assert isinstance(act1, str)
    files["stages/act1.yml"] = act1.replace(
        'id: "act1"',
        'id: "act1"\nallow_stage_regression: true',
    ).replace(
        '  - action: "dm_narrate"\n    text: "第一幕开始"',
        '  - action: "dm_narrate"\n    text: "第一幕开始"\n'
        '  - action: "transition_to"\n    stage_id: "prologue"',
    )
    package = load_package_archive(package_archive(files))
    engine = ScriptEngine.from_package(package)
    state = create_initial_state(
        session_id=str(uuid4()),
        script_id=package.package.id,
        player_id=str(uuid4()),
        player_character_id="player",
        entry_stage="act1",
    )

    # 当：第一幕处理已配置的向后跳转。
    state = await engine.run_action(state, action_id="request_advance")

    # 则：仅因严格阶段字段已启用，回退才会成功。
    assert state["current_stage"] == "prologue"
    assert state["completed_stages"] == []
    assert state["completed_acts"] == []


async def test_script_engine_marks_act_complete_after_its_final_stage_exits() -> None:
    # 给定：第一幕的最终阶段退出到复盘，且不会先触发结局。
    files = state_graph_package_files()
    act1 = files["stages/act1.yml"]
    assert isinstance(act1, str)
    files["stages/act1.yml"] = act1.replace(
        '  - type: "submission_correct"\n    field: "suspect"\n    value: "npc"',
        "  - type: always",
    )
    package = load_package_archive(package_archive(files))
    engine = ScriptEngine.from_package(package)
    state = create_initial_state(
        session_id=str(uuid4()),
        script_id=package.package.id,
        player_id=str(uuid4()),
        player_character_id="player",
        entry_stage="prologue",
    )

    # 当：流程退出分配给第一幕的两个阶段。
    state = await engine.run_action(state, action_id="request_advance")

    # 则：act_completed 条件可以观察权威的幕生命周期。
    assert state["current_stage"] == "review"
    assert state["completed_acts"] == ["book1"]


class RecordingEventSink:
    def __init__(self) -> None:
        self.actions: list[str] = []

    async def execute(
        self,
        action: str,
        payload: JsonMapping,
        *,
        idempotency_key: str,
    ) -> None:
        _ = payload
        _ = idempotency_key
        self.actions.append(action)
