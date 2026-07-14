"""定义玩家动作的严格请求与响应模型。"""

from typing import Literal

from pydantic import Field

from engine.api.schemas.common import (
    ActionType,
    ApiModel,
    DiscoveredClue,
    EventTrigger,
    MediaTrigger,
    StateChanges,
)

# ── 玩家行动请求 ──


class ActionRequest(ApiModel):
    """描述动作端点接受的一条玩家指令。"""

    action: ActionType = Field(description="Player action type.")
    character_id: str | None = Field(
        default=None, min_length=1, max_length=128, description="Target character ID."
    )
    message: str | None = Field(
        default=None, min_length=1, max_length=8000, description="Chat message."
    )
    scene_id: str | None = Field(
        default=None, min_length=1, max_length=128, description="Target scene ID."
    )
    hotspot_id: str | None = Field(
        default=None, min_length=1, max_length=128, description="Target hotspot ID."
    )
    evidence_id: str | None = Field(
        default=None, min_length=1, max_length=128, description="Target evidence ID."
    )
    card_id: str | None = Field(
        default=None, min_length=1, max_length=128, description="Target card ID."
    )
    target_character_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=128,
        description="Target character for card usage.",
    )
    reason: str | None = Field(
        default=None, min_length=1, max_length=2000, description="Advance request reason."
    )


# ── 行动响应类型 ──


class NpcResponse(ApiModel):
    """返回交谈动作生成的确定性 NPC 结果。"""

    type: Literal["npc_response"] = Field(description="Response discriminator.")
    character_id: str = Field(description="NPC character ID.")
    text: str = Field(description="NPC reply text.")
    emotion: str = Field(description="NPC emotion label.")
    state_changes: StateChanges = Field(description="NPC state deltas.")
    triggered_events: list[str] = Field(description="Triggered event IDs.")
    media_triggers: list[MediaTrigger] = Field(description="Media actions.")


class SceneResult(ApiModel):
    """返回场景搜索产生的发现和叙述。"""

    type: Literal["scene_result"] = Field(description="Response discriminator.")
    scene_id: str = Field(description="Scene ID.")
    hotspot_id: str = Field(description="Hotspot ID.")
    dm_narration: str = Field(description="DM narration text.")
    discovered_clues: list[DiscoveredClue] = Field(description="Newly found clues.")
    discovered_evidences: list[str] = Field(description="Newly found evidence IDs.")
    media_triggers: list[MediaTrigger] = Field(description="Media actions.")


class EvidenceReaction(ApiModel):
    """返回 NPC 对玩家出示证物的反应。"""

    type: Literal["evidence_reaction"] = Field(description="Response discriminator.")
    character_id: str = Field(description="NPC character ID.")
    text: str = Field(description="NPC reaction text.")
    emotion: str = Field(description="NPC emotion label.")
    state_changes: StateChanges = Field(description="NPC state deltas.")
    triggered_dialog: str = Field(description="Unlocked dialog branch ID.")
    media_triggers: list[MediaTrigger] = Field(description="Media actions.")


class CardResult(ApiModel):
    """返回卡牌已生效的效果和剩余使用次数。"""

    type: Literal["card_result"] = Field(description="Response discriminator.")
    card_id: str = Field(description="Used card ID.")
    remaining_uses: int = Field(description="Remaining uses.")
    effect: str = Field(description="Applied card effect ID.")
    character_id: str = Field(description="Target character ID.")
    text: str = Field(description="Narrative result text.")
    effect_description: str = Field(description="Human-readable effect summary.")


class StageTransitionState(ApiModel):
    """公开阶段跳转后的客户端可见状态。"""

    current_stage: str = Field(description="New current stage.")
    available_actions: list[ActionType] = Field(description="Allowed actions.")


class StageTransition(ApiModel):
    """返回成功的阶段跳转及其发出的事件。"""

    type: Literal["stage_transition"] = Field(description="Response discriminator.")
    from_stage: str = Field(description="Previous stage.")
    to_stage: str = Field(description="Next stage.")
    transition_events: list[EventTrigger] = Field(description="Transition events.")
    new_state: StageTransitionState = Field(description="Updated state summary.")


class AdvanceRequirement(ApiModel):
    """公开一个确定性阶段推进条件的当前完成状态。"""

    label: str = Field(description="Human-readable requirement label.")
    met: bool = Field(description="Whether the requirement is currently met.")


class AdvanceDenied(ApiModel):
    """说明当前阶段暂时无法推进的原因。"""

    type: Literal["advance_denied"] = Field(description="Response discriminator.")
    reason: str = Field(description="Why advance is currently denied.")
    hint: str = Field(description="Lightweight next-step hint.")
    suggested_action: ActionType = Field(description="Suggested action.")
    suggested_target: str = Field(description="Suggested target ID.")
    requirements: list[AdvanceRequirement] = Field(
        default_factory=list,
        description="Current deterministic advancement checklist.",
    )


# ── 最终推理提交 ──


class FinalSubmissionRequest(ApiModel):
    """记录首个垂直切片中玩家提交的确定性阶段判断。"""

    option: Literal["A", "B", "C", "D"] = Field(
        description="Selected judgment option."
    )


class SubmissionDetail(ApiModel):
    """公开判断选项及其被证据支持的边界说明。"""

    selected_option: Literal["A", "B", "C", "D"] = Field(
        description="Submitted judgment option."
    )
    correct_option: Literal["C"] = Field(description="Deterministic correct option.")
    evidence_boundary: str = Field(
        description="Why the evidence supports or rejects the option."
    )
    npc_disclosure: str | None = Field(
        default=None,
        description="Authorized NPC disclosure emitted only for the correct judgment.",
    )


class SubmissionResult(ApiModel):
    """返回已评分的阶段判断和稳定结果标识。"""

    type: Literal["submission_result"] = Field(description="Response discriminator.")
    correct: bool = Field(description="Overall correctness.")
    score: int = Field(description="Score from 0 to 100.")
    detail: SubmissionDetail = Field(description="Submission breakdown.")
    ending_id: str = Field(description="Triggered ending ID.")
    triggered_events: list[EventTrigger] = Field(description="Ending events.")


# ── 行动响应联合类型 ──

ActionResponse = (
    NpcResponse | SceneResult | EvidenceReaction | CardResult | StageTransition | AdvanceDenied
)
