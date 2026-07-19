"""定义 MP-2 房间大厅的严格 HTTP 请求与安全投影。"""

from datetime import datetime
from typing import Annotated, Literal, TypeAlias
from uuid import UUID

from pydantic import Field

from engine.api.schemas.common import ApiModel
from engine.api.schemas.sessions import CreateSessionRequest, CreateSessionResponse
from engine.contracts.multiplayer_v1.commands import (
    AssignCharacterCommand,
    CommandResultV1,
    ReadyCommand,
    StartRoomCommand,
    UnassignCharacterCommand,
)

# ── 创建与恢复 ──


class CreateMultiplayerSessionRequest(ApiModel):
    """请求从已发布双人剧本创建 lobby。"""

    mode: Literal["multiplayer_v1"]
    script_id: str = Field(min_length=1, max_length=128)


class CreateMultiplayerSessionResponse(ApiModel):
    """返回创建后的 host membership 和 lobby revision。"""

    session_id: UUID
    mode: Literal["multiplayer_v1"] = "multiplayer_v1"
    status: Literal["lobby"] = "lobby"
    revision: int = Field(ge=0)
    member_id: UUID
    created_at: datetime


CreateAnySessionRequest: TypeAlias = CreateSessionRequest | CreateMultiplayerSessionRequest
CreateAnySessionResponse: TypeAlias = CreateSessionResponse | CreateMultiplayerSessionResponse


class CurrentMultiplayerSession(ApiModel):
    """定位 principal 当前未完成的 multiplayer room。"""

    session_id: UUID
    mode: Literal["multiplayer_v1"] = "multiplayer_v1"
    status: Literal["lobby", "active"]


# ── 邀请 ──


class CreateRoomInviteRequest(ApiModel):
    ttl_seconds: int = Field(default=900, ge=60, le=3600)


class CreateRoomInviteResponse(ApiModel):
    invite_id: UUID
    token: str = Field(min_length=32)
    expires_at: datetime


class AcceptRoomInviteResponse(ApiModel):
    session_id: UUID
    status: Literal["lobby"] = "lobby"
    revision: int = Field(ge=0)
    member_id: UUID


class LobbyInvite(ApiModel):
    invite_id: UUID
    expires_at: datetime
    uses_count: int = Field(ge=0)
    max_uses: int = Field(ge=1)
    revoked: bool


# ── Lobby participant-safe snapshot ──


class LobbyPackageSummary(ApiModel):
    script_id: str
    title: str
    version: str


class LobbyCapacity(ApiModel):
    min_players: int = Field(ge=1)
    max_players: int = Field(ge=1)
    joined: int = Field(ge=0)


class LobbyMember(ApiModel):
    member_id: UUID
    room_role: Literal["host", "player"]
    character_id: str | None
    ready: bool


class LobbyCharacter(ApiModel):
    id: str
    name: str
    assigned_member_id: UUID | None


class LobbyCapabilities(ApiModel):
    can_invite: bool
    can_assign_character: bool
    can_ready: bool
    can_start: bool


class LobbySnapshotV1(ApiModel):
    session_id: UUID
    mode: Literal["multiplayer_v1"] = "multiplayer_v1"
    status: Literal["lobby", "active"]
    revision: int = Field(ge=0)
    package: LobbyPackageSummary
    capacity: LobbyCapacity
    self: LobbyMember
    members: tuple[LobbyMember, ...]
    characters: tuple[LobbyCharacter, ...]
    capabilities: LobbyCapabilities
    invites: tuple[LobbyInvite, ...] = ()


# MP-2 只执行大厅命令；阶段、hint 和 recovery 命令仍由严格总 union 解析后拒绝。
LobbyCommand: TypeAlias = Annotated[
    AssignCharacterCommand | UnassignCharacterCommand | ReadyCommand | StartRoomCommand,
    Field(discriminator="type"),
]

__all__ = [
    "AcceptRoomInviteResponse",
    "CreateAnySessionRequest",
    "CreateAnySessionResponse",
    "CreateMultiplayerSessionRequest",
    "CreateMultiplayerSessionResponse",
    "CreateRoomInviteRequest",
    "CreateRoomInviteResponse",
    "CurrentMultiplayerSession",
    "LobbyCapabilities",
    "LobbyCapacity",
    "LobbyCharacter",
    "LobbyCommand",
    "LobbyInvite",
    "LobbyMember",
    "LobbyPackageSummary",
    "LobbySnapshotV1",
    "CommandResultV1",
]
