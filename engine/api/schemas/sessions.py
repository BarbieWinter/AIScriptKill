"""定义游戏会话的严格请求与响应模型。"""

from typing import Literal

from pydantic import Field

from engine.api.schemas.common import ActionType, ApiModel, PendingMedia

# ── 会话创建 ──


class CreateSessionRequest(ApiModel):
    """描述用于启动会话的剧本和角色。"""

    script_id: str = Field(min_length=1, max_length=128, description="Script package ID.")
    player_name: str = Field(min_length=1, max_length=80, description="Player display name.")
    preferred_character_id: str = Field(
        min_length=1,
        max_length=128,
        description="Requested player character ID.",
    )


class CreateSessionResponse(ApiModel):
    """返回已创建会话的标识和初始状态。"""

    session_id: str = Field(description="Created game session ID.")
    script_id: str = Field(description="Script package ID.")
    status: str = Field(description="Session status.")
    current_stage: str = Field(description="Current stage ID.")
    player_character_id: str = Field(description="Selected player character ID.")
    available_actions: list[ActionType] = Field(description="Allowed actions.")
    created_at: str = Field(description="Creation timestamp.")


# ── 会话状态 ──


class SessionStateResponse(ApiModel):
    """公开游戏会话当前的客户端可见状态。"""

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
    viewed_evidences: list[str] = Field(description="Viewed evidence IDs.")
    current_scene: str = Field(description="Current scene ID.")
    pending_media: list[PendingMedia] = Field(description="Active media queue.")


# ── 会话恢复/维护 ──


class UpdateSessionRequest(ApiModel):
    """请求从持久化的 LangGraph 检查点恢复。"""

    action: Literal["restore"] = Field(description="Session maintenance action.")
    checkpoint_id: str = Field(
        min_length=1,
        max_length=128,
        description="Checkpoint ID used by restore actions.",
    )


class UpdateSessionResponse(ApiModel):
    """返回会话成功恢复后选定的状态。"""

    session_id: str = Field(description="Game session ID.")
    status: str = Field(description="Updated session status.")
    current_stage: str = Field(description="Restored current stage.")
    restored_from: str = Field(description="Checkpoint used for restoration.")
