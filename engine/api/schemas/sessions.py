from pydantic import Field

from engine.api.schemas.common import ActionType, ApiModel, PendingMedia

# ── 会话创建 ──


class CreateSessionRequest(ApiModel):
    script_id: str = Field(description="Script package ID.")
    player_name: str = Field(description="Player display name.")
    preferred_character_id: str = Field(description="Requested player character ID.")


class CreateSessionResponse(ApiModel):
    session_id: str = Field(description="Created game session ID.")
    script_id: str = Field(description="Script package ID.")
    status: str = Field(description="Session status.")
    current_stage: str = Field(description="Current stage ID.")
    player_character_id: str = Field(description="Selected player character ID.")
    available_actions: list[ActionType] = Field(description="Allowed actions.")
    created_at: str = Field(description="Creation timestamp.")


# ── 会话状态 ──


class SessionStateResponse(ApiModel):
    session_id: str = Field(description="Game session ID.")
    script_id: str = Field(description="Script package ID.")
    status: str = Field(description="Session status.")
    current_stage: str = Field(description="Current stage ID.")
    stage_name: str = Field(description="Display stage name.")
    player_character_id: str = Field(description="Selected player character ID.")
    available_actions: list[ActionType] = Field(description="Allowed actions.")
    available_characters: list[str] = Field(description="Character IDs in scene.")
    unlocked_clues_count: int = Field(description="Unlocked clue count.")
    total_clues_in_round: int = Field(description="Total clue count in current round.")
    discovered_evidences: list[str] = Field(description="Discovered evidence IDs.")
    current_scene: str = Field(description="Current scene ID.")
    pending_media: list[PendingMedia] = Field(description="Active media queue.")


# ── 会话恢复/维护 ──


class UpdateSessionRequest(ApiModel):
    action: str = Field(description="Session maintenance action.")
    checkpoint_id: str = Field(description="Checkpoint ID used by restore actions.")


class UpdateSessionResponse(ApiModel):
    session_id: str = Field(description="Game session ID.")
    status: str = Field(description="Updated session status.")
    current_stage: str = Field(description="Restored current stage.")
    restored_from: str = Field(description="Checkpoint used for restoration.")
