"""在完整 LangGraph 状态和公开会话投影之间转换。"""

from engine.api.schemas.common import ActionType, JsonValue
from engine.core.game_state import EvidencePresentation, GameState, create_initial_state
from engine.repositories.session_models import SessionRuntimeState, StoredSession


def initial_game_state(session: StoredSession) -> GameState:
    """以新会话投影创建首个可持久恢复的完整状态。"""

    state = create_initial_state(
        session_id=str(session.id),
        script_id=session.script_id,
        player_id=str(session.player_id) if session.player_id is not None else "anonymous",
        player_character_id=session.player_character_id or "player",
        entry_stage=session.state.current_stage,
    )
    _copy_projection_to_game_state(state, session.state)
    return state


def synchronize_monotonic_progress(
    state: GameState,
    projection: SessionRuntimeState,
) -> GameState:
    """将图外已读/已查看进度单调合并回权威图状态。"""

    _extend_unique(state["unlocked_clues"], projection.unlocked_clues)
    _extend_unique(state["discovered_evidences"], projection.discovered_evidences)
    _extend_unique(state["viewed_evidences"], projection.viewed_evidences)
    _extend_unique(
        state["unlocked_character_chapters"],
        projection.unlocked_character_chapters,
    )
    _extend_unique(state["read_character_chapters"], projection.read_character_chapters)
    _extend_presentations(
        state["evidences_shown_to_npcs"],
        projection.evidences_shown_to_npcs,
    )
    return state


def project_runtime_state(
    state: GameState,
    previous: SessionRuntimeState,
    *,
    stage_name: str,
) -> SessionRuntimeState:
    """从完整图状态生成兼容现有 REST 查询的有限投影。"""

    return SessionRuntimeState(
        player_name=previous.player_name,
        current_stage=state["current_stage"],
        stage_name=stage_name,
        available_actions=_action_types(state["available_actions"]),
        available_characters=list(state["available_characters"]),
        unlocked_clues=list(state["unlocked_clues"]),
        discovered_evidences=list(state["discovered_evidences"]),
        viewed_evidences=list(state["viewed_evidences"]),
        unlocked_character_chapters=list(state["unlocked_character_chapters"]),
        read_character_chapters=list(state["read_character_chapters"]),
        evidences_shown_to_npcs=[
            EvidencePresentation(
                evidence_id=item["evidence_id"],
                character_id=item["character_id"],
            )
            for item in state["evidences_shown_to_npcs"]
        ],
        current_scene=state["current_scene"],
        pending_media=[
            {
                "id": str(item.get("id", "")),
                "type": str(item.get("type", "")),
                "status": str(item.get("status", "")),
            }
            for item in state["pending_media"]
        ],
        final_submission=_final_submission(state),
        ending_id=state["ending_id"],
    )


def _copy_projection_to_game_state(
    state: GameState,
    projection: SessionRuntimeState,
) -> None:
    state["available_actions"] = list(projection.available_actions)
    state["available_characters"] = list(projection.available_characters)
    state["unlocked_clues"] = list(projection.unlocked_clues)
    state["discovered_evidences"] = list(projection.discovered_evidences)
    state["viewed_evidences"] = list(projection.viewed_evidences)
    state["unlocked_character_chapters"] = list(projection.unlocked_character_chapters)
    state["read_character_chapters"] = list(projection.read_character_chapters)
    state["evidences_shown_to_npcs"] = [
        EvidencePresentation(
            evidence_id=item["evidence_id"],
            character_id=item["character_id"],
        )
        for item in projection.evidences_shown_to_npcs
    ]
    state["current_scene"] = projection.current_scene
    state["pending_media"] = [dict(item) for item in projection.pending_media]
    state["final_submission"] = _game_final_submission(projection.final_submission)
    state["ending_id"] = projection.ending_id
    state["ending_triggered"] = projection.ending_id is not None


def _final_submission(state: GameState) -> dict[str, str | list[str]] | None:
    raw = state["final_submission"]
    if raw is None:
        return None
    result: dict[str, str | list[str]] = {}
    for key, value in raw.items():
        if isinstance(value, str):
            result[key] = value
        elif isinstance(value, list) and all(isinstance(item, str) for item in value):
            result[key] = [item for item in value if isinstance(item, str)]
    return result


def _game_final_submission(
    raw: dict[str, str | list[str]] | None,
) -> dict[str, JsonValue] | None:
    if raw is None:
        return None
    result: dict[str, JsonValue] = {}
    for key, value in raw.items():
        if isinstance(value, str):
            result[key] = value
        else:
            result[key] = [item for item in value]
    return result


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


def _extend_unique(target: list[str], additions: list[str]) -> None:
    for item in additions:
        if item not in target:
            target.append(item)


def _extend_presentations(
    target: list[EvidencePresentation],
    additions: list[EvidencePresentation],
) -> None:
    for item in additions:
        if item not in target:
            target.append(
                EvidencePresentation(
                    evidence_id=item["evidence_id"],
                    character_id=item["character_id"],
                )
            )
