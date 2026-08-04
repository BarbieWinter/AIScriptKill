"""Participant-safe room-event replay and discussion-history wire models."""

from uuid import UUID

from pydantic import Field

from engine.api.schemas.common import ApiModel
from engine.api.schemas.multiplayer_rooms import RoomSnapshotV1


class ParticipantRoomEvent(ApiModel):
    """A durable public room event; event_id is the consumer deduplication key."""

    event_id: UUID
    sequence: int = Field(ge=1)
    revision: int = Field(ge=0)
    event_type: str = Field(min_length=1)
    event_version: int = Field(ge=1)
    payload: dict[str, object]


class ParticipantRoomEventPage(ApiModel):
    """A bounded ascending replay page plus the HTTP recovery authority."""

    revision: int = Field(ge=0)
    event_head_sequence: int = Field(ge=0)
    snapshot: RoomSnapshotV1
    events: tuple[ParticipantRoomEvent, ...]
    next_after_sequence: int = Field(ge=0)
    has_more: bool
    reset_required: bool = False
    available_from_sequence: int = Field(ge=0)


class DiscussionHistoryPage(ApiModel):
    """A bounded ascending page of already-public discussion messages."""

    event_head_sequence: int = Field(ge=0)
    events: tuple[ParticipantRoomEvent, ...]
    next_after_sequence: int = Field(ge=0)
    has_more: bool
    reset_required: bool = False
    available_from_sequence: int = Field(ge=0)
