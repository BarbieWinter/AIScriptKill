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
    action: ActionType = Field(description="Player action type.")
    character_id: str | None = Field(default=None, description="Target character ID.")
    message: str | None = Field(default=None, description="Chat message.")
    scene_id: str | None = Field(default=None, description="Target scene ID.")
    hotspot_id: str | None = Field(default=None, description="Target hotspot ID.")
    evidence_id: str | None = Field(default=None, description="Target evidence ID.")
    card_id: str | None = Field(default=None, description="Target card ID.")
    target_character_id: str | None = Field(
        default=None,
        description="Target character for card usage.",
    )
    reason: str | None = Field(default=None, description="Advance request reason.")


# ── 行动响应类型 ──


class NpcResponse(ApiModel):
    type: Literal["npc_response"] = Field(description="Response discriminator.")
    character_id: str = Field(description="NPC character ID.")
    text: str = Field(description="NPC reply text.")
    emotion: str = Field(description="NPC emotion label.")
    state_changes: StateChanges = Field(description="NPC state deltas.")
    triggered_events: list[str] = Field(description="Triggered event IDs.")
    media_triggers: list[MediaTrigger] = Field(description="Media actions.")


class SceneResult(ApiModel):
    type: Literal["scene_result"] = Field(description="Response discriminator.")
    scene_id: str = Field(description="Scene ID.")
    hotspot_id: str = Field(description="Hotspot ID.")
    dm_narration: str = Field(description="DM narration text.")
    discovered_clues: list[DiscoveredClue] = Field(description="Newly found clues.")
    discovered_evidences: list[str] = Field(description="Newly found evidence IDs.")
    media_triggers: list[MediaTrigger] = Field(description="Media actions.")


class EvidenceReaction(ApiModel):
    type: Literal["evidence_reaction"] = Field(description="Response discriminator.")
    character_id: str = Field(description="NPC character ID.")
    text: str = Field(description="NPC reaction text.")
    emotion: str = Field(description="NPC emotion label.")
    state_changes: StateChanges = Field(description="NPC state deltas.")
    triggered_dialog: str = Field(description="Unlocked dialog branch ID.")
    media_triggers: list[MediaTrigger] = Field(description="Media actions.")


class CardResult(ApiModel):
    type: Literal["card_result"] = Field(description="Response discriminator.")
    card_id: str = Field(description="Used card ID.")
    remaining_uses: int = Field(description="Remaining uses.")
    effect: str = Field(description="Applied card effect ID.")
    character_id: str = Field(description="Target character ID.")
    text: str = Field(description="Narrative result text.")
    effect_description: str = Field(description="Human-readable effect summary.")


class StageTransitionState(ApiModel):
    current_stage: str = Field(description="New current stage.")
    available_actions: list[ActionType] = Field(description="Allowed actions.")


class StageTransition(ApiModel):
    type: Literal["stage_transition"] = Field(description="Response discriminator.")
    from_stage: str = Field(description="Previous stage.")
    to_stage: str = Field(description="Next stage.")
    transition_events: list[EventTrigger] = Field(description="Transition events.")
    new_state: StageTransitionState = Field(description="Updated state summary.")


class AdvanceDenied(ApiModel):
    type: Literal["advance_denied"] = Field(description="Response discriminator.")
    reason: str = Field(description="Why advance is currently denied.")
    hint: str = Field(description="Lightweight next-step hint.")
    suggested_action: ActionType = Field(description="Suggested action.")
    suggested_target: str = Field(description="Suggested target ID.")


# ── 最终推理提交 ──


class FinalSubmissionRequest(ApiModel):
    suspect: str = Field(description="Accused suspect ID.")
    motive: str = Field(description="Submitted motive.")
    key_evidences: list[str] = Field(description="Submitted evidence IDs.")
    deduction: str = Field(description="Free-form deduction chain.")


class SubmissionDetail(ApiModel):
    correct_suspect: bool = Field(description="Whether suspect is correct.")
    correct_motive: bool = Field(description="Whether motive is correct.")
    key_evidence_hit_rate: str = Field(description="Hit count string.")
    missed_key_evidences: list[str] = Field(description="Missed evidence IDs.")


class SubmissionResult(ApiModel):
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
