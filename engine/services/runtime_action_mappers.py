"""将 REST 动作转换为核心图输入，并将图状态差量映射回现有响应。"""

from dataclasses import dataclass

from engine.api.schemas import (
    ActionRequest,
    ActionResponse,
    AdvanceDenied,
    AdvanceRequirement,
    CardResult,
    EvidenceReaction,
    NpcResponse,
    SceneResult,
    StageTransition,
)
from engine.api.schemas.actions import StageTransitionState
from engine.api.schemas.common import ActionType, DiscoveredClue, EventTrigger, MediaTrigger
from engine.core.condition_evaluator import evaluate_condition
from engine.core.game_state import GameState
from engine.core.package_schema import ScriptPackageImport
from engine.core.package_validation_context import metadata_text
from engine.core.script_action_runtime import examine_scene_target
from engine.repositories.session_models import (
    ChatMessageDraft,
    DiscoveryDraft,
    SessionActionEffect,
)


@dataclass(frozen=True, slots=True)
class RuntimeActionInput:
    action_id: ActionType
    target: str | None
    text: str | None


def runtime_action_input(payload: ActionRequest) -> RuntimeActionInput:
    """将分字段 REST 载荷编码为核心图的窄动作契约。"""

    match payload.action:
        case "talk_to_npc":
            return RuntimeActionInput(payload.action, payload.character_id, payload.message)
        case "examine_scene":
            target = payload.scene_id
            if payload.scene_id is not None and payload.hotspot_id is not None:
                target = examine_scene_target(payload.scene_id, payload.hotspot_id)
            return RuntimeActionInput(payload.action, target, None)
        case "show_evidence":
            target = None
            if payload.evidence_id is not None and payload.character_id is not None:
                target = f"{payload.evidence_id}:{payload.character_id}"
            return RuntimeActionInput(payload.action, target, None)
        case "use_card":
            return RuntimeActionInput(payload.action, payload.card_id, None)
        case "open_clue_board":
            return RuntimeActionInput(payload.action, None, None)
        case "request_advance":
            return RuntimeActionInput(payload.action, "request_advance", None)


def runtime_action_result(
    payload: ActionRequest,
    previous: GameState,
    current: GameState,
    package: ScriptPackageImport,
) -> tuple[ActionResponse, SessionActionEffect]:
    """根据真实图执行结果生成现有 API 联合响应和关系表差量。"""

    effect = SessionActionEffect(
        state_patch={},
        chat_messages=_new_chat_messages(previous, current),
        discoveries=_new_discoveries(previous, current),
    )
    match payload.action:
        case "talk_to_npc":
            character_id = payload.character_id or ""
            response = _latest_npc_response(previous, current, character_id)
            return response, effect
        case "examine_scene":
            return _scene_result(payload, previous, current, package), effect
        case "show_evidence":
            return _evidence_reaction(payload, previous, current), effect
        case "use_card":
            return _card_result(payload), effect
        case "request_advance":
            return _advance_result(previous, current, package), effect
        case "open_clue_board":
            return (
                AdvanceDenied(
                    type="advance_denied",
                    reason="线索板由前端本地视图打开，后端仅返回当前线索数据。",
                    hint="调用 /sessions/{session_id}/clues 获取线索列表。",
                    suggested_action="examine_scene",
                    suggested_target=current["current_scene"] or "start",
                ),
                effect,
            )


def _latest_npc_response(
    previous: GameState,
    current: GameState,
    character_id: str,
) -> NpcResponse:
    messages = current["chat_history"][len(previous["chat_history"]) :]
    for message in reversed(messages):
        if message["role"] == "npc" and message["character_id"] == character_id:
            return NpcResponse(
                type="npc_response",
                character_id=character_id,
                text=message["text"],
                emotion=message["emotion"] or "normal",
                state_changes={},
                triggered_events=_new_completed_events(previous, current),
                media_triggers=_new_media(previous, current),
            )
    return NpcResponse(
        type="npc_response",
        character_id=character_id,
        text="",
        emotion="normal",
        state_changes={},
        triggered_events=_new_completed_events(previous, current),
        media_triggers=_new_media(previous, current),
    )


def _scene_result(
    payload: ActionRequest,
    previous: GameState,
    current: GameState,
    package: ScriptPackageImport,
) -> SceneResult:
    new_clue_ids = _new_items(previous["unlocked_clues"], current["unlocked_clues"])
    clue_names = {clue.id: clue.name for clue in package.clues}
    return SceneResult(
        type="scene_result",
        scene_id=current["current_scene"],
        hotspot_id=payload.hotspot_id or "",
        dm_narration=_latest_dm_text(previous, current),
        discovered_clues=[
            DiscoveredClue(clue_id=clue_id, name=clue_names.get(clue_id, clue_id))
            for clue_id in new_clue_ids
        ],
        discovered_evidences=_new_items(
            previous["discovered_evidences"],
            current["discovered_evidences"],
        ),
        media_triggers=_new_media(previous, current),
    )


def _evidence_reaction(
    payload: ActionRequest,
    previous: GameState,
    current: GameState,
) -> EvidenceReaction:
    character_id = payload.character_id or ""
    response = _latest_npc_response(previous, current, character_id)
    return EvidenceReaction(
        type="evidence_reaction",
        character_id=character_id,
        text=response.text,
        emotion=response.emotion,
        state_changes=response.state_changes,
        triggered_dialog=(current["triggered_dialogs"][-1] if current["triggered_dialogs"] else ""),
        media_triggers=response.media_triggers,
    )


def _card_result(payload: ActionRequest) -> CardResult:
    return CardResult(
        type="card_result",
        card_id=payload.card_id or "",
        remaining_uses=0,
        effect="applied",
        character_id=payload.target_character_id or "",
        text="卡牌已应用。",
        effect_description="效果已写入游戏状态。",
    )


def _advance_result(
    previous: GameState,
    current: GameState,
    package: ScriptPackageImport,
) -> ActionResponse:
    if current["current_stage"] != previous["current_stage"]:
        transition_events = [
            EventTrigger(
                action=record["action"],
                asset_id=metadata_text(record["payload"].get("asset_id")),
                text=metadata_text(record["payload"].get("text")),
            )
            for record in current["event_log"][len(previous["event_log"]) :]
            if record["action"] in ("play_audio", "dm_narrate")
        ]
        return StageTransition(
            type="stage_transition",
            from_stage=previous["current_stage"],
            to_stage=current["current_stage"],
            transition_events=transition_events,
            new_state=StageTransitionState(
                current_stage=current["current_stage"],
                available_actions=_action_types(current["available_actions"]),
            ),
        )
    requirements = _advance_requirements(current, package)
    missing = [item.label for item in requirements if not item.met]
    return AdvanceDenied(
        type="advance_denied",
        reason="当前阶段的推进条件尚未满足。",
        hint=f"还需完成：{'、'.join(missing)}。" if missing else "请完成当前阶段目标后再推进。",
        suggested_action=_suggested_action(current),
        suggested_target=_suggested_target(current),
        requirements=requirements,
    )


def _advance_requirements(
    state: GameState,
    package: ScriptPackageImport,
) -> list[AdvanceRequirement]:
    stage = next((item for item in package.stages if item.id == state["current_stage"]), None)
    if stage is None:
        return []
    result: list[AdvanceRequirement] = []
    for condition in _requirement_conditions(stage.definition.get("exit_conditions")):
        result.append(
            AdvanceRequirement(
                label=_requirement_label(condition, package),
                met=evaluate_condition(condition, state),
            )
        )
    return result


def _requirement_conditions(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    flattened: list[dict[str, object]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        condition = {str(key): raw for key, raw in item.items()}
        if condition.get("type") == "all" and isinstance(condition.get("conditions"), list):
            flattened.extend(_requirement_conditions(condition["conditions"]))
        else:
            flattened.append(condition)
    return flattened


def _requirement_label(
    condition: dict[str, object],
    package: ScriptPackageImport,
) -> str:
    condition_type = condition.get("type")
    if condition_type == "clue_discovered":
        clue_id = str(condition.get("clue_id", ""))
        clue = next((item for item in package.clues if item.id == clue_id), None)
        return f"发现线索「{clue.name if clue is not None else clue_id}」"
    if condition_type == "evidence_viewed":
        evidence_id = str(condition.get("evidence_id", ""))
        evidence = next((item for item in package.evidences if item.id == evidence_id), None)
        return f"查看证物「{evidence.name if evidence is not None else evidence_id}」"
    if condition_type == "evidence_shown_to_npc":
        evidence_id = str(condition.get("evidence_id", ""))
        character_id = str(condition.get("character_id", ""))
        evidence = next((item for item in package.evidences if item.id == evidence_id), None)
        character = next((item for item in package.characters if item.id == character_id), None)
        evidence_name = evidence.name if evidence is not None else evidence_id
        character_name = character.name if character is not None else character_id
        return f"向{character_name}出示「{evidence_name}」"
    if condition_type == "character_chapter_read":
        chapter_id = str(condition.get("chapter_id", ""))
        chapter = next((item for item in package.chapters if item.id == chapter_id), None)
        return f"阅读人物章节「{chapter.title if chapter is not None else chapter_id}」"
    if condition_type == "character_talked_to":
        character_id = str(condition.get("character_id", ""))
        character = next((item for item in package.characters if item.id == character_id), None)
        return f"与{character.name if character is not None else character_id}交谈"
    if condition_type == "player_requested":
        return "点击推进"
    return str(condition_type or "完成阶段目标")


def _new_chat_messages(
    previous: GameState,
    current: GameState,
) -> tuple[ChatMessageDraft, ...]:
    drafts: list[ChatMessageDraft] = []
    if len(current["player_utterances"]) > len(previous["player_utterances"]):
        drafts.append(ChatMessageDraft(role="player", text=current["player_utterances"][-1]))
    for message in current["chat_history"][len(previous["chat_history"]) :]:
        drafts.append(
            ChatMessageDraft(
                role=message["role"],
                character_id=message["character_id"],
                text=message["text"],
                emotion=message["emotion"],
                message_id=message["id"],
            )
        )
    return tuple(drafts)


def _new_discoveries(
    previous: GameState,
    current: GameState,
) -> tuple[DiscoveryDraft, ...]:
    discoveries = [
        DiscoveryDraft(entity_type="clue", entity_id=item)
        for item in _new_items(previous["unlocked_clues"], current["unlocked_clues"])
    ]
    discoveries.extend(
        DiscoveryDraft(entity_type="evidence", entity_id=item)
        for item in _new_items(
            previous["discovered_evidences"], current["discovered_evidences"]
        )
    )
    discoveries.extend(
        DiscoveryDraft(entity_type="character_chapter", entity_id=item)
        for item in _new_items(
            previous["unlocked_character_chapters"],
            current["unlocked_character_chapters"],
        )
    )
    return tuple(discoveries)


def _latest_dm_text(previous: GameState, current: GameState) -> str:
    for message in reversed(current["chat_history"][len(previous["chat_history"]) :]):
        if message["role"] == "dm":
            return message["text"]
    return ""


def _new_media(previous: GameState, current: GameState) -> list[MediaTrigger]:
    return [
        MediaTrigger(action="play_audio", asset_id=str(item.get("id", "")))
        for item in current["pending_media"][len(previous["pending_media"]) :]
    ]


def _new_completed_events(previous: GameState, current: GameState) -> list[str]:
    return _new_items(previous["completed_events"], current["completed_events"])


def _new_items(previous: list[str], current: list[str]) -> list[str]:
    return [item for item in current if item not in previous]


def _suggested_action(state: GameState) -> ActionType:
    actions = _action_types(state["available_actions"])
    if actions:
        return actions[0]
    return "open_clue_board"


def _action_types(values: list[str]) -> list[ActionType]:
    supported = (
        "talk_to_npc",
        "examine_scene",
        "show_evidence",
        "use_card",
        "open_clue_board",
        "request_advance",
    )
    return [value for value in values if value in supported]


def _suggested_target(state: GameState) -> str:
    action = _suggested_action(state)
    if action == "talk_to_npc" and state["available_characters"]:
        return state["available_characters"][0]
    if action == "examine_scene" and state["available_scenes"]:
        return state["available_scenes"][0]
    return ""
