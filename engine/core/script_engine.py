from dataclasses import dataclass
from typing import Literal

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from engine.api.schemas.common import ActionType
from engine.core.checkpoint import checkpoint_config
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
from engine.core.script_engine_errors import (
    ScriptEngineGraphError,
    ScriptEngineGraphResultError,
)
from engine.core.script_runtime import (
    PackageRuntimeIndex,
    record_dialog,
    record_evidence_presentation,
)

type ActionRoute = Literal["npc_response", "check_conditions", "ending"]
type TransitionRoute = Literal["stage_exit", "ending", "end"]
type GameCheckpointer = BaseCheckpointSaver[str] | BaseCheckpointSaver[int]
type CompiledGameGraph = CompiledStateGraph[GameState, None, GameState, GameState]


@dataclass(frozen=True, slots=True)
class ScriptEngine:
    package: ScriptPackageImport
    event_bus: EventBus
    runtime: PackageRuntimeIndex
    graph: CompiledGameGraph | None

    @classmethod
    def from_archive(cls, archive_bytes: bytes) -> "ScriptEngine":
        return cls.from_package(load_package_archive(archive_bytes))

    @classmethod
    def from_package(
        cls,
        package: ScriptPackageImport,
        *,
        event_sink: EventActionSink | None = None,
        checkpointer: GameCheckpointer | None = None,
    ) -> "ScriptEngine":
        event_bus = EventBus(package, event_sink)
        runtime = PackageRuntimeIndex(package)
        engine = cls(
            package=package,
            event_bus=event_bus,
            runtime=runtime,
            graph=None,
        )
        return cls(
            package=package,
            event_bus=event_bus,
            runtime=runtime,
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
        next_state = clone_game_state(state)
        next_state["pending_action"] = PlayerActionInput(
            action_id=action_id,
            target=target,
            text=text,
        )
        graph = self._compiled_graph()
        result = await graph.ainvoke(
            next_state,
            checkpoint_config(thread_id or state["session_id"]),
        )
        if isinstance(result, dict):
            values = {str(key): json_value(value) for key, value in result.items()}
            return game_state_from_mapping(values)
        raise ScriptEngineGraphResultError()

    async def restore_state(self, *, thread_id: str) -> GameState | None:
        snapshot = await self._compiled_graph().aget_state(checkpoint_config(thread_id))
        if not isinstance(snapshot.values, dict) or len(snapshot.values) == 0:
            return None
        values = {str(key): json_value(value) for key, value in snapshot.values.items()}
        return game_state_from_mapping(values)

    def _build_graph(
        self,
        checkpointer: GameCheckpointer | None,
    ) -> CompiledGameGraph:
        builder = StateGraph(GameState)
        builder.add_node("stage_entry", self.stage_entry)
        builder.add_node("player_action", self.player_action)
        builder.add_node("npc_response", self.npc_response)
        builder.add_node("check_conditions", self.check_conditions)
        builder.add_node("process_events", self.process_events)
        builder.add_node("stage_exit", self.stage_exit)
        builder.add_node("ending", self.ending)
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
        builder.add_edge("stage_exit", "stage_entry")
        builder.add_edge("ending", END)
        return builder.compile(checkpointer=checkpointer)

    async def stage_entry(self, state: GameState) -> GameState:
        # 读取 current_stage、stage_entered_at 和 stage 定义：如果这是本阶段首次进入，
        # 写入 stage_entered_at/current_time、可用动作/场景/角色，并触发 on_stage_entry。
        # 如果本轮只是同一阶段内的玩家动作，则不重复触发 entry 事件，避免音频/解锁重复。
        next_state = clone_game_state(state)
        stage = self.runtime.stage_by_id(next_state["current_stage"])
        self.runtime.apply_stage_runtime(next_state, stage)
        if next_state["stage_entered_at"] != "":
            return next_state
        timestamp = current_timestamp()
        next_state["stage_entered_at"] = timestamp
        next_state["current_time"] = timestamp
        return await self.event_bus.on_stage_entry(next_state, stage)

    async def player_action(self, state: GameState) -> GameState:
        # 读取 pending_action 和当前阶段的 available_actions：没有动作时说明这是阶段切换
        # 后的自动 stage_entry 落点，只清理后继续检查条件；有动作时写入 performed_actions、
        # player_requests、对话计数或证据/卡牌记录，供条件 DSL 后续读取。
        next_state = clone_game_state(state)
        action = next_state["pending_action"]
        if action is None:
            return next_state
        if not self._action_allowed(next_state, action["action_id"]):
            next_state["pending_action"] = None
            return next_state
        next_state["performed_actions"].append(
            {"action_id": action["action_id"], "target": action["target"]},
        )
        match action["action_id"]:
            case "request_advance":
                next_state["player_requests"].append(action["target"] or "request_advance")
            case "talk_to_npc":
                record_dialog(next_state, action["target"], action["text"])
            case "examine_scene":
                next_state["current_scene"] = action["target"] or next_state["current_scene"]
            case "show_evidence":
                record_evidence_presentation(next_state, action["target"])
            case "use_card":
                next_state["used_cards"].append(
                    {"card_id": action["target"] or "", "card_type": None}
                )
            case "open_clue_board":
                pass
        return next_state

    async def npc_response(self, state: GameState) -> GameState:
        # 读取刚处理过的 talk_to_npc pending_action 和 chat_history：当前版本先写入一个
        # 确定性 mock NPC 回复，后续 AI Agent 可以替换这里的生成逻辑而不改变图结构。
        next_state = clone_game_state(state)
        action = next_state["pending_action"]
        if action is None or action["target"] is None:
            return next_state
        message_id = f"{next_state['session_id']}:npc:{len(next_state['chat_history'])}"
        next_state["pending_npc_responses"].append(
            {"character_id": action["target"], "text": "NPC 正在回应。"},
        )
        next_state["chat_history"].append(
            {
                "id": message_id,
                "role": "npc",
                "character_id": action["target"],
                "text": "NPC 正在回应。",
                "emotion": None,
                "timestamp": current_timestamp(),
            },
        )
        return next_state

    async def check_conditions(self, state: GameState) -> GameState:
        # 读取 final_submission、endings 和当前 stage.exit_conditions：结局条件优先，
        # 命中后写入 ending_triggered/ending_id 和待处理 ending on_trigger；否则评估
        # 阶段退出条件，命中后写入 next_stage，交给 process_events/_should_transition。
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
        # 读取 pending_events：这些事件来自 ending on_trigger 或未来节点排队的脚本事件。
        # 写入 completed_events/event_log/pending_media/解锁状态，并清空 pending_events。
        return await self.event_bus.process_events(state)

    async def stage_exit(self, state: GameState) -> GameState:
        # 读取 current_stage 和 next_stage：先触发当前 stage 的 on_stage_exit，然后把
        # current_stage 推进到 next_stage，记录 previous/completed/history，并清空
        # stage_entered_at，让下一次 stage_entry 触发新阶段 entry 事件。
        next_state = clone_game_state(state)
        target_stage = next_state["next_stage"]
        if target_stage is None:
            return next_state
        current_stage = self.runtime.stage_by_id(next_state["current_stage"])
        next_state = await self.event_bus.on_stage_exit(next_state, current_stage)
        if current_stage.id not in next_state["completed_stages"]:
            next_state["completed_stages"].append(current_stage.id)
        next_state["previous_stage"] = current_stage.id
        next_state["current_stage"] = target_stage
        next_state["next_stage"] = None
        next_state["pending_action"] = None
        next_state["stage_entered_at"] = ""
        next_state["condition_cache"] = {}
        next_state["stage_history"].append(target_stage)
        return next_state

    async def ending(self, state: GameState) -> GameState:
        # 读取 ending_triggered/ending_id：这是图的终止节点，只清空本轮动作和事件队列，
        # 保留 final_submission、媒体队列和 event_log，供 API 响应与复盘读取。
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
        # 分支3：talk_to_npc 需要 NPC 回复节点，其余动作都直接进入条件检查。
        if action["action_id"] == "talk_to_npc":
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

    def _action_allowed(self, state: GameState, action_id: str) -> bool:
        return len(state["available_actions"]) == 0 or action_id in state["available_actions"]

    def _compiled_graph(self) -> CompiledGameGraph:
        if self.graph is None:
            raise ScriptEngineGraphError()
        return self.graph


def current_timestamp() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat()
