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


# ── 会话展示投影 ──


class SessionPresentationStage(ApiModel):
    """只公开当前阶段可供玩家使用的展示字段。"""

    id: str = Field(description="Current stage ID.")
    name: str = Field(description="Current stage display name.")
    available_actions: list[ActionType] = Field(description="Player actions enabled now.")
    available_characters: list[str] = Field(description="Character IDs available now.")


class SessionPresentationHotspot(ApiModel):
    """公开一个可渲染热点，但不携带其服务端执行规则。"""

    id: str = Field(description="Hotspot ID.")
    label: str = Field(description="Hotspot display label.")
    x: float = Field(description="Horizontal scene coordinate.")
    y: float = Field(description="Vertical scene coordinate.")
    width: float | None = Field(default=None, description="Optional hotspot width.")
    height: float | None = Field(default=None, description="Optional hotspot height.")


class SessionPresentationScene(ApiModel):
    """公开当前场景的安全视觉投影。"""

    id: str = Field(description="Current scene ID.")
    name: str = Field(description="Current scene display name.")
    description: str | None = Field(default=None, description="Optional public description.")
    ambient_color: str | None = Field(default=None, description="Optional ambient CSS color.")
    background_url: str | None = Field(
        default=None,
        description="Optional browser-safe HTTP(S) or same-origin background URL.",
    )
    hotspots: list[SessionPresentationHotspot] = Field(description="Ordered public hotspots.")


class SessionPresentationJudgementOption(ApiModel):
    """公开一个有序判断选项。"""

    id: str = Field(description="Judgement option ID.")
    text: str = Field(description="Judgement option display text.")


class SessionPresentationJudgement(ApiModel):
    """公开当前阶段可作答的问题，绝不包含正确答案。"""

    title: str | None = Field(default=None, description="Optional judgement title.")
    question: str = Field(description="Judgement question.")
    options: list[SessionPresentationJudgementOption] = Field(
        description="Options in package-declared order."
    )


class SessionPresentationResponse(ApiModel):
    """返回从已发布运行时包投影出的当前玩家展示。"""

    stage: SessionPresentationStage
    scene: SessionPresentationScene
    judgement: SessionPresentationJudgement | None = None


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
