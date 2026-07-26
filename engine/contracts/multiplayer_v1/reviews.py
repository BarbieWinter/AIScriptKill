"""定义仅在正常完成后开放的 Multiplayer v1 复盘契约。"""

from typing import Annotated, Final, Literal, TypeAlias
from uuid import UUID

from pydantic import Field

from engine.contracts.multiplayer_v1.base import ContractModel, Identifier
from engine.contracts.multiplayer_v1.state import RevealedBallot, RevealedOptionCount

REVIEW_VERSION: Final = 1


class ReviewChapter(ContractModel):
    """通关后开放的一章参与角色剧本。"""

    id: Identifier
    character_id: Identifier
    title: str
    content: str


class ReviewEnding(ContractModel):
    """本局最终选中的创作结局。"""

    id: Identifier
    name: str
    outcome_text: str


class ReviewTimelineEntry(ContractModel):
    """通关后允许公开的一项权威时间线事实。"""

    time: str
    event: str
    hidden: bool


class ReviewAlternativeEnding(ContractModel):
    """真相文件中允许在复盘展示的替代结局。"""

    id: Identifier
    condition: str
    news_broadcast: str | None = None


class ReviewTruth(ContractModel):
    """从 DM 真相中显式白名单投影出的完整案情。"""

    case_summary: str | None = None
    murderer: Identifier | None = None
    victim: Identifier | None = None
    motive: str | None = None
    timeline: tuple[ReviewTimelineEntry, ...] = ()
    key_evidence_chain: tuple[str, ...] = ()
    alternative_endings: tuple[ReviewAlternativeEnding, ...] = ()


class _ReviewSettlementBase(ContractModel):
    stage_id: Identifier
    settlement_id: Identifier
    outcome_id: Identifier


class NamedBallotsReview(_ReviewSettlementBase):
    reveal: Literal["named_ballots"]
    ballots: tuple[RevealedBallot, ...] = Field(min_length=1)


class AggregateReview(_ReviewSettlementBase):
    reveal: Literal["aggregate"]
    option_counts: tuple[RevealedOptionCount, ...] = Field(min_length=1)


class OutcomeOnlyReview(_ReviewSettlementBase):
    reveal: Literal["outcome_only"]


ReviewSettlementReveal: TypeAlias = Annotated[
    NamedBallotsReview | AggregateReview | OutcomeOnlyReview,
    Field(discriminator="reveal"),
]


class CompletedReviewV1(ContractModel):
    """正常完成后可由一个房间参与者读取的白名单复盘。"""

    review_version: Literal[1]
    session_id: UUID
    member_id: Identifier
    ending: ReviewEnding
    chapters: tuple[ReviewChapter, ...]
    truth: ReviewTruth
    final_settlement: ReviewSettlementReveal
