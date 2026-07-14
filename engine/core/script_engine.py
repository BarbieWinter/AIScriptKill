"""构建并执行 LangGraph 剧本游戏状态机。"""

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Literal, cast

from langgraph.checkpoint.base import BaseCheckpointSaver

# LangGraph 发布包保留了类型注解但未声明 py.typed；仅在导入边界抑制缺失存根诊断。
from langgraph.graph import END, START, StateGraph  # pyright: ignore[reportMissingTypeStubs]
from langgraph.graph.state import (  # pyright: ignore[reportMissingTypeStubs]
    CompiledStateGraph,
)

from engine.agents.npc_agent import DeterministicNpcResponder, NpcResponder
from engine.api.schemas.common import ActionType
from engine.core.checkpoint import checkpoint_config
from engine.core.clock import SYSTEM_CLOCK, Clock
from engine.core.event_bus import EventActionSink, EventBus
from engine.core.game_state import (
    GameState,
    PlayerActionInput,
    clone_game_state,
)
from engine.core.game_state_codec import game_state_from_mapping
from engine.core.package_archive import json_value
from engine.core.package_loader import load_package_archive
from engine.core.package_schema import ScriptPackageImport
from engine.core.script_action_runtime import (
    apply_player_action,
    parse_evidence_target,
    parse_examine_scene_target,
    validate_player_action,
)
from engine.core.script_engine_errors import (
    ScriptEngineActionError,
    ScriptEngineGraphError,
    ScriptEngineGraphResultError,
)
from engine.core.script_runtime import PackageRuntimeIndex

type ActionRoute = Literal["npc_response", "check_conditions", "ending"]
type TransitionRoute = Literal["stage_exit", "ending", "end"]
type StageExitRoute = Literal["stage_entry", "end"]
type GameCheckpointer = BaseCheckpointSaver[str] | BaseCheckpointSaver[int]
type CompiledGameGraph = CompiledStateGraph[GameState, None, GameState, GameState]


@dataclass(frozen=True, slots=True)
class ScriptEngine:
    """持有已编译游戏图及其不可变剧本包协作者。"""

    package: ScriptPackageImport
    event_bus: EventBus
    runtime: PackageRuntimeIndex
    clock: Clock
    npc_responder: NpcResponder
    graph: CompiledGameGraph | None

    @classmethod
    def from_archive(cls, archive_bytes: bytes) -> "ScriptEngine":
        """校验归档并构建不带持久化适配器的引擎。"""

        return cls.from_package(load_package_archive(archive_bytes))

    @classmethod
    def from_package(
        cls,
        package: ScriptPackageImport,
        *,
        event_sink: EventActionSink | None = None,
        checkpointer: GameCheckpointer | None = None,
        npc_responder: NpcResponder | None = None,
        clock: Clock = SYSTEM_CLOCK,
    ) -> "ScriptEngine":
        """使用可选事件、NPC 和检查点适配器构建并编译引擎。"""

        event_bus = EventBus(package, event_sink, clock)
        runtime = PackageRuntimeIndex(package)
        resolved_npc_responder = npc_responder or DeterministicNpcResponder()
        engine = cls(
            package=package,
            event_bus=event_bus,
            runtime=runtime,
            clock=clock,
            npc_responder=resolved_npc_responder,
            graph=None,
        )
        return cls(
            package=package,
            event_bus=event_bus,
            runtime=runtime,
            clock=clock,
            npc_responder=resolved_npc_responder,
            graph=engine._build_graph(checkpointer),
        )

    async def run_action(
        self,
        state: GameState,
        *,
        action_id: ActionType,
        target: str | None = None,
        text: str | None = None,
        thread_id: str | None = None,
    ) -> GameState:
        """校验玩家动作、写入检查点并执行至图运行完成。"""

        next_state = clone_game_state(state)
        action = PlayerActionInput(
            action_id=action_id,
            target=target,
            text=text,
        )
        self.runtime.apply_stage_runtime(
            next_state,
            self.runtime.stage_by_id(next_state["current_stage"]),
        )
        # LangGraph 会在 player_action 节点前保存图输入。这里提前校验，避免被拒绝的动作
        # 成为最新持久状态并破坏进程恢复。
        validate_player_action(next_state, action)
        next_state["current_time"] = self.clock.now()
        next_state["pending_action"] = action
        graph = self._compiled_graph()
        # LangGraph 的 Command 泛型未完整标注，但 values 模式的结果仍在下方执行运行时校验。
        raw_result: object = await graph.ainvoke(  # pyright: ignore[reportUnknownMemberType]
            next_state,
            checkpoint_config(thread_id or state["session_id"]),
        )
        if isinstance(raw_result, dict):
            result = cast(Mapping[object, object], raw_result)
            values = {
                str(key): json_value(value, f"graph_result.{key}") for key, value in result.items()
            }
            return game_state_from_mapping(values)
        raise ScriptEngineGraphResultError()

    async def restore_state(self, *, thread_id: str) -> GameState | None:
        """恢复线程最新持久状态，缺失时返回 None。"""

        snapshot = await self._compiled_graph().aget_state(checkpoint_config(thread_id))
        raw_values: object = snapshot.values
        if not isinstance(raw_values, dict):
            return None
        snapshot_values = cast(Mapping[object, object], raw_values)
        if len(snapshot_values) == 0:
            return None
        values = {
            str(key): json_value(value, f"checkpoint_state.{key}")
            for key, value in snapshot_values.items()
        }
        return game_state_from_mapping(values)

    def _build_graph(
        self,
        checkpointer: GameCheckpointer | None,
    ) -> CompiledGameGraph:
        builder = StateGraph(GameState)
        # LangGraph 的 cache_policy 泛型未完整标注；这里只暴露游戏节点需要的窄调用契约。
        add_node = cast(
            Callable[[str, Callable[[GameState], Awaitable[GameState]]], object],
            builder.add_node,  # pyright: ignore[reportUnknownMemberType]
        )
        add_node("stage_entry", self.stage_entry)
        add_node("player_action", self.player_action)
        add_node("npc_response", self.npc_response)
        add_node("check_conditions", self.check_conditions)
        add_node("process_events", self.process_events)
        add_node("stage_exit", self.stage_exit)
        add_node("ending", self.ending)
        builder.add_edge(START, "stage_entry")
        builder.add_edge("stage_entry", "player_action")
        builder.add_conditional_edges(
            "player_action",
            self._route_action,
            {
                "npc_response": "npc_response",
                "check_conditions": "check_conditions",
                "ending": "ending",
            },
        )
        builder.add_edge("npc_response", "check_conditions")
        builder.add_edge("check_conditions", "process_events")
        builder.add_conditional_edges(
            "process_events",
            self._should_transition,
            {"stage_exit": "stage_exit", "ending": "ending", "end": END},
        )
        builder.add_conditional_edges(
            "stage_exit",
            self._route_stage_exit,
            {"stage_entry": "stage_entry", "end": END},
        )
        builder.add_edge("ending", END)
        # LangGraph 的检查点泛型在公开签名中仍为 Unknown，返回值由方法注解固定为游戏图。
        return builder.compile(  # pyright: ignore[reportUnknownMemberType]
            checkpointer=checkpointer
        )

    async def stage_entry(self, state: GameState) -> GameState:
        """进入当前阶段，但不重复播放进入效果。

        读取当前阶段、进入时间戳和阶段定义。首次进入时写入时间和可用玩法字段，
        随后应用进入事件；否则返回克隆状态，不重复产生媒体或解锁效果。
        """

        next_state = clone_game_state(state)
        stage = self.runtime.stage_by_id(next_state["current_stage"])
        self.runtime.apply_stage_runtime(next_state, stage)
        next_state = await self.event_bus.unlock_game_start_chapters(next_state)
        if next_state["stage_entered_at"] != "":
            return next_state
        timestamp = next_state["current_time"] or self.clock.now()
        next_state["stage_entered_at"] = timestamp
        next_state["current_time"] = timestamp
        return await self.event_bus.on_stage_entry(next_state, stage)

    async def player_action(self, state: GameState) -> GameState:
        """将待处理玩家动作应用到条件可见状态。

        读取待处理动作和阶段可用项。写入已执行动作、请求、对话次数、场景选择、
        证物出示或卡牌使用；跳转后无动作的自动进入会保持克隆状态不变。
        """

        next_state = clone_game_state(state)
        action = next_state["pending_action"]
        if action is None:
            return next_state
        apply_player_action(next_state, action)
        if action["action_id"] == "examine_scene":
            scene_id, hotspot_id = parse_examine_scene_target(action["target"])
            if hotspot_id is not None:
                actions = self.runtime.scene_hotspot_actions(scene_id, hotspot_id)
                if actions is None:
                    raise ScriptEngineActionError(
                        "ACTION_TARGET_UNAVAILABLE",
                        f"场景热点不可用: {scene_id}:{hotspot_id}",
                    )
                next_state = await self.event_bus.process_actions(
                    next_state,
                    f"scene:{scene_id}:hotspot:{hotspot_id}",
                    actions,
                    source="scene_hotspot",
                )
        return next_state

    async def npc_response(self, state: GameState) -> GameState:
        """调用受包内事实约束的 NPC 生成器并追加稳定消息记录。"""

        next_state = clone_game_state(state)
        action = next_state["pending_action"]
        if action is None or action["target"] is None:
            return next_state
        character_id = action["target"]
        player_text = action["text"] or ""
        if action["action_id"] == "show_evidence":
            evidence_id, character_id = parse_evidence_target(action["target"])
            evidence = next(
                (item for item in self.package.evidences if item.id == evidence_id),
                None,
            )
            player_text = (
                f"玩家向你出示证物「{evidence.name if evidence is not None else evidence_id}」。"
                "只根据已授权的证物反应作答。"
            )
        reply = await self.npc_responder.respond(
            next_state,
            self.package,
            character_id=character_id,
            player_text=player_text,
        )
        message_id = f"{next_state['session_id']}:npc:{len(next_state['chat_history'])}"
        next_state["pending_npc_responses"].append(
            {"character_id": character_id, "text": reply.text},
        )
        next_state["chat_history"].append(
            {
                "id": message_id,
                "role": "npc",
                "character_id": character_id,
                "text": reply.text,
                "emotion": reply.emotion,
                "timestamp": self.clock.now(),
            },
        )
        return next_state

    async def check_conditions(self, state: GameState) -> GameState:
        """按优先顺序求值结局条件和阶段退出条件。

        读取最终提交、结局和当前阶段条件。结局匹配时写入结局状态和触发事件；
        否则在退出条件匹配时写入下一阶段。
        """

        next_state = clone_game_state(state)
        ending = self.runtime.matching_ending(next_state)
        if ending is not None:
            next_state["ending_triggered"] = True
            next_state["ending_id"] = ending.id
            next_state["pending_events"].append(
                {
                    "event_id": f"ending:{ending.id}",
                    "actions": [dict(action) for action in ending.on_trigger],
                    "source": "ending",
                },
            )
            return next_state
        if self.runtime.stage_exit_condition_met(next_state):
            next_state["next_stage"] = self.runtime.next_stage_id(next_state["current_stage"])
        return next_state

    async def process_events(self, state: GameState) -> GameState:
        """排空已入队剧本事件并结束当前动作。

        读取待处理事件，通过 EventBus 应用其有序效果，写入事件日志、媒体和解锁变更，
        随后清除待处理玩家动作。
        """

        next_state = await self.event_bus.process_events(state)
        next_state["pending_action"] = None
        return next_state

    async def stage_exit(self, state: GameState) -> GameState:
        """校验并执行请求的阶段跳转。

        读取当前阶段、目标阶段及目标进入条件。跳转受阻时记录原因并结束本回合；
        成功时应用退出事件，写入已完成阶段/幕历史，推进当前阶段，并为下一节点清除进入时间。
        """

        next_state = clone_game_state(state)
        target_stage = next_state["next_stage"]
        if target_stage is None:
            return next_state
        current_stage = self.runtime.stage_by_id(next_state["current_stage"])
        is_regression = self.runtime.stage_index(target_stage) < self.runtime.stage_index(
            current_stage.id
        )
        # 前进目标的守卫条件可以看到即将完成的阶段/幕；回退只是重新进入旧阶段，
        # 不能因此新增完成记录。守卫拒绝跳转时，两类候选状态都不会被提交。
        candidate_state = clone_game_state(next_state)
        if not is_regression:
            if current_stage.id not in candidate_state["completed_stages"]:
                candidate_state["completed_stages"].append(current_stage.id)
            completed_act = self.runtime.completed_act_for_stage(current_stage.id)
            if completed_act is not None and completed_act not in candidate_state["completed_acts"]:
                candidate_state["completed_acts"].append(completed_act)
        if not self.runtime.stage_entry_conditions_met(candidate_state, target_stage):
            next_state["blocked_transitions"].append(
                {
                    "from_stage": current_stage.id,
                    "to_stage": target_stage,
                    "reason": "entry_conditions_not_met",
                },
            )
            next_state["next_stage"] = None
            next_state["pending_action"] = None
            return next_state
        next_state = await self.event_bus.on_stage_exit(candidate_state, current_stage)
        next_state["previous_stage"] = current_stage.id
        next_state["current_stage"] = target_stage
        next_state["next_stage"] = None
        next_state["pending_action"] = None
        next_state["player_requests"] = []
        next_state["stage_entered_at"] = ""
        next_state["condition_cache"] = {}
        next_state["stage_history"].append(target_stage)
        return next_state

    async def ending(self, state: GameState) -> GameState:
        """在保留结局结果的同时收尾图内队列。

        读取选定结局状态并清除待处理动作、事件和跳转；最终提交、媒体和事件历史仍可供
        API 使用方读取。
        """

        next_state = clone_game_state(state)
        next_state["pending_action"] = None
        next_state["pending_events"] = []
        next_state["next_stage"] = None
        return next_state

    def _route_action(self, state: GameState) -> ActionRoute:
        # 分支1：结局已触发时，任何玩家动作都不再进入普通流程，直接进入 ending。
        if state["ending_triggered"]:
            return "ending"
        action = state["pending_action"]
        # 分支2：阶段切换后的自动 stage_entry 没有玩家动作，需要继续跑条件/事件收尾。
        if action is None:
            return "check_conditions"
        # 分支3：交谈和出示证物都需要 NPC 回复节点。
        if action["action_id"] in ("talk_to_npc", "show_evidence"):
            return "npc_response"
        return "check_conditions"

    def _should_transition(self, state: GameState) -> TransitionRoute:
        # 分支1：ending on_trigger 已处理完成，直接进入 ending 终止节点。
        if state["ending_triggered"]:
            return "ending"
        # 分支2：条件或事件设置了 next_stage，需要先执行 stage_exit 再进入下一阶段。
        if state["next_stage"] is not None:
            return "stage_exit"
        # 分支3：没有阶段变化，结束本次图执行，等待下一次玩家动作。
        return "end"

    def _route_stage_exit(self, state: GameState) -> StageExitRoute:
        # 成功切换会清空进入时间并执行新阶段入口；被入口条件拦截时结束本轮，
        # 避免仍为真的旧阶段退出条件在图内形成自动重试循环。
        if state["stage_entered_at"] == "":
            return "stage_entry"
        return "end"

    def _compiled_graph(self) -> CompiledGameGraph:
        if self.graph is None:
            raise ScriptEngineGraphError()
        return self.graph
