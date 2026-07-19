"""定义尚未接入 package loader 的 Multiplayer v1 创作契约。"""

from typing import Annotated, Final, Literal, Self, TypeAlias

from pydantic import Field, TypeAdapter, model_validator

from engine.contracts.multiplayer_v1.base import ContractModel, Identifier
from engine.contracts.multiplayer_v1.vocabulary import (
    CharacterAssignmentPolicy,
    DiscussionClosePolicy,
    FinalAnswerMode,
    SettlementEffect,
    SettlementMode,
    SettlementReveal,
    StartPolicy,
    SubmissionChangePolicy,
)

PublicMaterialRevealAt: TypeAlias = Annotated[
    str,
    Field(pattern=r"^(stage_enter|all_players_read|settlement_done|outcome:.+)$"),
]


class MultiplayerPolicy(ContractModel):
    """声明多人剧本允许的人数、选角唯一性和开局门槛。"""

    min_players: int = Field(ge=2)
    max_players: int = Field(ge=2)
    character_assignment: CharacterAssignmentPolicy = CharacterAssignmentPolicy.REQUIRED
    start_policy: StartPolicy = StartPolicy.ALL_PLAYERS_READY
    duplicate_characters: Literal[False] = False

    @model_validator(mode="after")
    def validate_player_range(self) -> Self:
        if self.min_players > self.max_players:
            raise ValueError("min_players must be less than or equal to max_players")
        return self


class SettlementOption(ContractModel):
    """声明结算中可选择的稳定选项 ID 和参与者文案。"""

    id: Identifier
    text: str = Field(min_length=1)


class _SettlementWithOptions(ContractModel):
    settlement_id: Identifier
    question: str = Field(min_length=1)
    options: tuple[SettlementOption, ...] = Field(min_length=1)
    reveal: SettlementReveal
    submission_change: SubmissionChangePolicy
    default_effect: SettlementEffect

    @model_validator(mode="after")
    def validate_unique_option_ids(self) -> Self:
        option_ids = [option.id for option in self.options]
        if len(option_ids) != len(set(option_ids)):
            raise ValueError("settlement option ids must be unique")
        return self


class NoSettlementDefinition(ContractModel):
    """声明阶段没有玩家结算动作。"""

    mode: Literal[SettlementMode.NONE]
    default_effect: SettlementEffect = SettlementEffect.RECORD_AND_CONTINUE


class SecretVoteSettlementDefinition(_SettlementWithOptions):
    """声明每名成员的选项在揭晓前保持私有。"""

    mode: Literal[SettlementMode.SECRET_VOTE]
    reveal: SettlementReveal = SettlementReveal.NAMED_BALLOTS
    submission_change: SubmissionChangePolicy = SubmissionChangePolicy.FORBIDDEN
    default_effect: SettlementEffect = SettlementEffect.RECORD_AND_CONTINUE


class SharedChoiceSettlementDefinition(_SettlementWithOptions):
    """声明房间成员共同确认一个共享选项。"""

    mode: Literal[SettlementMode.SHARED_CHOICE]
    reveal: SettlementReveal = SettlementReveal.OUTCOME_ONLY
    submission_change: SubmissionChangePolicy = SubmissionChangePolicy.ALLOWED_BEFORE_COMPLETE
    default_effect: SettlementEffect = SettlementEffect.RECORD_AND_CONTINUE


class FinalJudgmentSettlementDefinition(_SettlementWithOptions):
    """声明可驱动结局分支的最终判断。"""

    mode: Literal[SettlementMode.FINAL_JUDGMENT]
    answer_mode: FinalAnswerMode
    reveal: SettlementReveal = SettlementReveal.NAMED_BALLOTS
    submission_change: SubmissionChangePolicy = SubmissionChangePolicy.FORBIDDEN
    default_effect: SettlementEffect = SettlementEffect.BRANCH


StageSettlementDefinition: TypeAlias = Annotated[
    NoSettlementDefinition
    | SecretVoteSettlementDefinition
    | SharedChoiceSettlementDefinition
    | FinalJudgmentSettlementDefinition,
    Field(discriminator="mode"),
]
STAGE_SETTLEMENT_ADAPTER: Final[TypeAdapter[StageSettlementDefinition]] = TypeAdapter(
    StageSettlementDefinition
)


class PublicMaterialDefinition(ContractModel):
    """声明公共素材及其确定性揭晓节点。"""

    id: Identifier
    reveal_at: PublicMaterialRevealAt


class DiscussionDefinition(ContractModel):
    """声明公共文字讨论的建议时长与关闭规则。"""

    suggested_minutes: int | None = Field(default=None, gt=0)
    close_policy: DiscussionClosePolicy = DiscussionClosePolicy.ALL_PLAYERS


class HintDefinition(ContractModel):
    """声明需要全员同意后逐级公开的三级提示。"""

    id: Identifier
    levels: tuple[Annotated[str, Field(min_length=1)], ...] = Field(
        min_length=3,
        max_length=3,
    )


class MultiplayerStageDefinition(ContractModel):
    """组合一个多人阶段的私有章节、公共材料、讨论、结算和提示。"""

    id: Identifier
    chapters: dict[Identifier, Identifier]
    public_materials: tuple[PublicMaterialDefinition, ...] = ()
    discussion: DiscussionDefinition
    settlement: StageSettlementDefinition
    hints: tuple[HintDefinition, ...] = ()

    @model_validator(mode="after")
    def validate_local_ids(self) -> Self:
        material_ids = [material.id for material in self.public_materials]
        if len(material_ids) != len(set(material_ids)):
            raise ValueError("public material ids must be unique")
        hint_ids = [hint.id for hint in self.hints]
        if len(hint_ids) != len(set(hint_ids)):
            raise ValueError("hint ids must be unique")
        return self


MULTIPLAYER_STAGE_ADAPTER: Final[TypeAdapter[MultiplayerStageDefinition]] = TypeAdapter(
    MultiplayerStageDefinition
)
