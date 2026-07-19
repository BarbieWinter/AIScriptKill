"""定义 Multiplayer v1 的参与者可见事件流。"""

from typing import Annotated, Final, Literal, Self, TypeAlias
from uuid import UUID

from pydantic import Field, TypeAdapter, model_validator

from engine.contracts.multiplayer_v1.base import (
    ContractModel,
    Identifier,
    UniqueIdentifierTuple,
)
from engine.contracts.multiplayer_v1.vocabulary import AudienceScope, RoomStatus, StagePhase


class EventAudience(ContractModel):
    """声明事件属于全房间或单个成员，禁止含糊的私有标记。"""

    scope: AudienceScope
    member_id: Identifier | None = None

    @model_validator(mode="after")
    def validate_member_scope(self) -> Self:
        if self.scope is AudienceScope.MEMBER and self.member_id is None:
            raise ValueError("member audience requires member_id")
        if self.scope is AudienceScope.ROOM and self.member_id is not None:
            raise ValueError("room audience forbids member_id")
        return self


class _EventBase(ContractModel):
    """提供全部参与者事件共享的顺序、修订和可见性字段。"""

    event_id: UUID
    session_id: UUID
    sequence: int = Field(ge=0)
    revision: int = Field(ge=0)
    audience: EventAudience


class RoomStatusChangedEvent(_EventBase):
    type: Literal["room.status_changed"]
    status: RoomStatus


class RoomCharacterAssignedEvent(_EventBase):
    type: Literal["room.character_assigned"]
    member_id: Identifier
    character_id: Identifier | None


class StagePhaseChangedEvent(_EventBase):
    type: Literal["stage.phase_changed"]
    stage_id: Identifier
    phase: StagePhase


class StageReadStatusChangedEvent(_EventBase):
    type: Literal["stage.read_status_changed"]
    stage_id: Identifier
    member_id: Identifier
    confirmed: bool


class DiscussionCloseStatusChangedEvent(_EventBase):
    type: Literal["discussion.close_status_changed"]
    stage_id: Identifier
    member_id: Identifier
    confirmed: bool


class DiscussionMessageCreatedEvent(_EventBase):
    type: Literal["discussion.message_created"]
    message_id: UUID
    stage_id: Identifier
    member_id: Identifier
    text: str = Field(min_length=1, max_length=4_000)


class SettlementSubmissionStatusChangedEvent(_EventBase):
    type: Literal["settlement.submission_status_changed"]
    settlement_id: Identifier
    submitted_member_ids: UniqueIdentifierTuple


class SettlementRevealedEvent(_EventBase):
    type: Literal["settlement.revealed"]
    settlement_id: Identifier
    outcome_id: Identifier


class ChapterGrantedEvent(_EventBase):
    type: Literal["chapter.granted"]
    member_id: Identifier
    character_id: Identifier
    chapter_id: Identifier

    @model_validator(mode="after")
    def require_matching_member_audience(self) -> Self:
        if (
            self.audience.scope is not AudienceScope.MEMBER
            or self.audience.member_id != self.member_id
        ):
            raise ValueError("chapter grants require the matching member audience")
        return self


ParticipantEvent: TypeAlias = Annotated[
    RoomStatusChangedEvent
    | RoomCharacterAssignedEvent
    | StagePhaseChangedEvent
    | StageReadStatusChangedEvent
    | DiscussionCloseStatusChangedEvent
    | DiscussionMessageCreatedEvent
    | SettlementSubmissionStatusChangedEvent
    | SettlementRevealedEvent
    | ChapterGrantedEvent,
    Field(discriminator="type"),
]
EVENT_ADAPTER: Final[TypeAdapter[ParticipantEvent]] = TypeAdapter(ParticipantEvent)
