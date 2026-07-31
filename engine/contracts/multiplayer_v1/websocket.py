"""定义 Multiplayer v1 WebSocket 帧，不绑定当前心跳处理器。"""

from typing import Annotated, Final, Literal, TypeAlias
from uuid import UUID

from pydantic import Field, TypeAdapter

from engine.contracts.multiplayer_v1.base import ContractModel, Identifier
from engine.contracts.multiplayer_v1.errors import MultiplayerErrorCode
from engine.contracts.multiplayer_v1.events import ParticipantEvent
from engine.contracts.multiplayer_v1.snapshots import ParticipantSnapshotV1

WS_PROTOCOL_VERSION: Final = 1


class ConnectionHelloData(ContractModel):
    protocol_version: Literal[1]
    ticket: str = Field(min_length=32, max_length=256)
    last_event_sequence: int | None = Field(default=None, ge=0)


class ConnectionHelloFrame(ContractModel):
    type: Literal["connection.hello"]
    data: ConnectionHelloData


class ConnectionReadyData(ContractModel):
    protocol_version: Literal[1]
    session_id: UUID
    member_id: Identifier
    revision: int = Field(ge=0)
    event_head_sequence: int = Field(ge=0)


class ConnectionReadyFrame(ContractModel):
    type: Literal["connection.ready"]
    data: ConnectionReadyData


class SessionPingData(ContractModel):
    pass


class SessionPingFrame(ContractModel):
    type: Literal["session.ping"]
    data: SessionPingData = Field(default_factory=SessionPingData)


class SessionPongData(ContractModel):
    session_id: UUID


class SessionPongFrame(ContractModel):
    type: Literal["session.pong"]
    data: SessionPongData


class RoomEventData(ContractModel):
    event: ParticipantEvent


class RoomEventFrame(ContractModel):
    type: Literal["room.event"]
    data: RoomEventData


class ReplayGapData(ContractModel):
    expected_next_sequence: int = Field(ge=0)
    available_from_sequence: int = Field(ge=0)
    event_head_sequence: int = Field(ge=0)


class ReplayGapFrame(ContractModel):
    type: Literal["replay.gap"]
    data: ReplayGapData


class ResyncRequiredData(ContractModel):
    reason: MultiplayerErrorCode
    snapshot: ParticipantSnapshotV1


class ResyncRequiredFrame(ContractModel):
    type: Literal["sync.resync_required"]
    data: ResyncRequiredData


ClientFrame: TypeAlias = Annotated[
    ConnectionHelloFrame | SessionPingFrame,
    Field(discriminator="type"),
]
ServerFrame: TypeAlias = Annotated[
    ConnectionReadyFrame | SessionPongFrame | RoomEventFrame | ReplayGapFrame | ResyncRequiredFrame,
    Field(discriminator="type"),
]
CLIENT_FRAME_ADAPTER: Final[TypeAdapter[ClientFrame]] = TypeAdapter(ClientFrame)
SERVER_FRAME_ADAPTER: Final[TypeAdapter[ServerFrame]] = TypeAdapter(ServerFrame)
