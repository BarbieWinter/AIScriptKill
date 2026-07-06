from engine.api.schemas import CreateSessionResponse, SessionStateResponse, UpdateSessionResponse
from engine.api.schemas.common import PendingMedia
from engine.repositories.session_repository import StoredSession
from engine.services.mapper_utils import timestamp

# ── 会话响应映射 ──


def create_response(session: StoredSession) -> CreateSessionResponse:
    return CreateSessionResponse(
        session_id=str(session.id),
        script_id=session.script_id,
        status=session.status,
        current_stage=session.state.current_stage,
        player_character_id=session.player_character_id,
        available_actions=session.state.available_actions,
        created_at=timestamp(session.created_at),
    )


# ── 当前状态响应 ──


def state_response(session: StoredSession, stage_name: str | None) -> SessionStateResponse:
    state = session.state
    return SessionStateResponse(
        session_id=str(session.id),
        script_id=session.script_id,
        status=session.status,
        current_stage=state.current_stage,
        stage_name=stage_name or state.stage_name,
        player_character_id=session.player_character_id,
        available_actions=state.available_actions,
        available_characters=state.available_characters,
        unlocked_clues_count=len(state.unlocked_clues),
        total_clues_in_round=max(len(state.unlocked_clues), 0),
        discovered_evidences=state.discovered_evidences,
        current_scene=state.current_scene,
        pending_media=[
            PendingMedia(id=item["id"], type=item["type"], status=item["status"])
            for item in state.pending_media
        ],
    )


# ── 检查点恢复响应 ──


def restore_response(session: StoredSession, checkpoint_id: str) -> UpdateSessionResponse:
    return UpdateSessionResponse(
        session_id=str(session.id),
        status="restored",
        current_stage=session.state.current_stage,
        restored_from=checkpoint_id,
    )
