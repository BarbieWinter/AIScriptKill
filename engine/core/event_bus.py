from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Protocol

from engine.core.game_state import GameState, clone_game_state
from engine.core.package_schema import JsonMapping, ScriptPackageImport, StageRecord
from engine.core.package_validation_context import json_mapping_list, metadata_text, metadata_texts
from engine.core.script_runtime import PackageRuntimeIndex


class EventActionSink(Protocol):
    async def execute(self, action: str, payload: JsonMapping) -> None:
        pass


@dataclass(frozen=True, slots=True)
class EventBus:
    package: ScriptPackageImport
    sink: EventActionSink | None = None
    _runtime: PackageRuntimeIndex = field(init=False, repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "_runtime", PackageRuntimeIndex(self.package))

    async def on_stage_entry(self, state: GameState, stage: StageRecord) -> GameState:
        return await self.process_actions(
            state,
            f"stage:{stage.id}:entry",
            json_mapping_list(stage.definition.get("on_stage_entry")),
        )

    async def on_stage_exit(self, state: GameState, stage: StageRecord) -> GameState:
        return await self.process_actions(
            state,
            f"stage:{stage.id}:exit",
            json_mapping_list(stage.definition.get("on_stage_exit")),
        )

    async def on_clue_discovered(self, state: GameState, clue_id: str) -> GameState:
        next_state = clone_game_state(state)
        stage = self._runtime.stage_by_id(next_state["current_stage"])
        for trigger in json_mapping_list(stage.definition.get("on_clue_discovered")):
            condition = trigger.get("condition")
            if not isinstance(condition, dict):
                continue
            if condition.get("clue_id") != clue_id:
                continue
            next_state = await self.process_actions(
                next_state,
                f"stage:{stage.id}:clue:{clue_id}",
                json_mapping_list(trigger.get("then")),
            )
        for trigger in json_mapping_list(stage.definition.get("media_triggers")):
            if trigger.get("event") != "clue_discovered" or trigger.get("clue_id") != clue_id:
                continue
            next_state = await self.process_actions(
                next_state,
                f"stage:{stage.id}:media:{clue_id}",
                json_mapping_list(trigger.get("then")),
            )
        return next_state

    async def process_events(self, state: GameState) -> GameState:
        next_state = clone_game_state(state)
        events = list(next_state["pending_events"])
        next_state["pending_events"] = []
        for event in events:
            next_state = await self.process_actions(
                next_state,
                event["event_id"],
                event["actions"],
                source=event["source"],
            )
        return next_state

    async def process_actions(
        self,
        state: GameState,
        event_id: str,
        actions: list[JsonMapping],
        source: str | None = None,
    ) -> GameState:
        next_state = clone_game_state(state)
        for index, action_payload in enumerate(actions):
            action = metadata_text(action_payload.get("action"))
            if action is None:
                continue
            action_event_id = metadata_text(action_payload.get("event_id")) or f"{event_id}:{index}"
            next_state = await self._execute_action(
                next_state,
                action_event_id,
                source or event_id,
                action,
                action_payload,
            )
        return next_state

    async def _execute_action(
        self,
        state: GameState,
        event_id: str,
        source: str,
        action: str,
        payload: JsonMapping,
    ) -> GameState:
        next_state = clone_game_state(state)
        if self.sink is not None:
            await self.sink.execute(action, payload)
        match action:
            case "dm_narrate":
                self._append_dm_message(
                    next_state, event_id, metadata_text(payload.get("text")) or ""
                )
            case "play_audio":
                self._queue_media(next_state, payload)
            case "unlock_scenes":
                self._unlock_scenes(next_state, metadata_texts(payload.get("scene_ids")))
            case "unlock_clue_round":
                await self._unlock_clue_round(next_state, metadata_text(payload.get("round_id")))
            case "clue_discover":
                await self._unlock_clue(next_state, metadata_text(payload.get("clue_id")))
            case "npc_enter_scene":
                self._update_npc_scene(
                    next_state,
                    metadata_text(payload.get("character_id")),
                    metadata_text(payload.get("scene_id")),
                )
            case "npc_emotion":
                self._update_npc_emotion(
                    next_state,
                    metadata_text(payload.get("character_id")),
                    metadata_text(payload.get("state")) or metadata_text(payload.get("emotion")),
                )
            case "transition_to":
                self._request_transition(next_state, metadata_text(payload.get("stage_id")))
            case "save_checkpoint" | "show_truth_summary":
                pass
            case _:
                return next_state
        self._record_event(next_state, event_id, source, action, payload)
        return next_state

    def _append_dm_message(self, state: GameState, event_id: str, text: str) -> None:
        state["chat_history"].append(
            {
                "id": event_id,
                "role": "dm",
                "character_id": None,
                "text": text,
                "emotion": None,
                "timestamp": _now(),
            },
        )

    def _queue_media(self, state: GameState, payload: JsonMapping) -> None:
        asset_id = metadata_text(payload.get("asset_id"))
        if asset_id is None:
            return
        state["pending_media"].append(
            {
                "id": asset_id,
                "type": metadata_text(payload.get("type")) or "audio",
                "status": "queued",
            },
        )

    def _unlock_scenes(self, state: GameState, scene_ids: tuple[str, ...]) -> None:
        for scene_id in scene_ids:
            if scene_id not in state["unlocked_scenes"]:
                state["unlocked_scenes"].append(scene_id)

    async def _unlock_clue_round(self, state: GameState, round_id: str | None) -> None:
        if round_id is None:
            return
        for clue in self.package.clues:
            if clue.round_id == round_id:
                await self._unlock_clue(state, clue.id)

    async def _unlock_clue(self, state: GameState, clue_id: str | None) -> None:
        if clue_id is None or clue_id in state["unlocked_clues"]:
            return
        clue = self._runtime.clue_by_id(clue_id)
        state["unlocked_clues"].append(clue.id)
        state["discovered_clues"].append(
            {
                "clue_id": clue.id,
                "round_id": clue.round_id,
                "scene_id": metadata_text(clue.metadata.get("related_scene")) or "",
                "is_key": clue.is_key,
            },
        )
        state.update(await self.on_clue_discovered(state, clue.id))

    def _update_npc_scene(
        self,
        state: GameState,
        character_id: str | None,
        scene_id: str | None,
    ) -> None:
        if character_id is None or scene_id is None:
            return
        npc_state = dict(state["npc_states"].get(character_id, {}))
        npc_state["scene_id"] = scene_id
        state["npc_states"][character_id] = npc_state
        state["npc_agents"][character_id] = npc_state

    def _update_npc_emotion(
        self,
        state: GameState,
        character_id: str | None,
        emotion: str | None,
    ) -> None:
        if character_id is None or emotion is None:
            return
        npc_state = dict(state["npc_states"].get(character_id, {}))
        npc_state["current_mood"] = emotion
        state["npc_states"][character_id] = npc_state
        state["npc_agents"][character_id] = npc_state

    def _request_transition(self, state: GameState, target_stage: str | None) -> None:
        if target_stage is None:
            return
        if self._runtime.can_transition(state, target_stage):
            state["next_stage"] = target_stage
            return
        state["blocked_transitions"].append(
            {
                "from_stage": state["current_stage"],
                "to_stage": target_stage,
                "reason": "stage_jump_denied",
            },
        )

    def _record_event(
        self,
        state: GameState,
        event_id: str,
        source: str,
        action: str,
        payload: JsonMapping,
    ) -> None:
        if event_id not in state["completed_events"]:
            state["completed_events"].append(event_id)
        state["event_log"].append(
            {"event_id": event_id, "source": source, "action": action, "payload": dict(payload)},
        )


def _now() -> str:
    return datetime.now(UTC).isoformat()
