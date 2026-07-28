"""定义 MP-2 房间大厅的严格 HTTP 请求与安全投影。"""

from datetime import datetime
from typing import Annotated, Literal, Self, TypeAlias
from uuid import UUID

from pydantic import Field, StrictBool, field_validator, model_validator

from engine.api.schemas.common import ApiModel
from engine.api.schemas.sessions import CreateSessionRequest, CreateSessionResponse
from engine.contracts.multiplayer_v1.commands import (
    AssignCharacterCommand,
    CommandResultV1,
    MultiplayerCommand,
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
    public_description: str
    assigned_member_id: UUID | None


class LobbyCapabilities(ApiModel):
    can_invite: bool
    can_assign_character: bool
    can_ready: bool
    can_start: bool
    can_end_incomplete: bool


class LobbySnapshotV1(ApiModel):
    session_id: UUID
    mode: Literal["multiplayer_v1"] = "multiplayer_v1"
    status: Literal["lobby"]
    revision: int = Field(ge=0)
    package: LobbyPackageSummary
    capacity: LobbyCapacity
    self: LobbyMember
    members: tuple[LobbyMember, ...]
    characters: tuple[LobbyCharacter, ...]
    capabilities: LobbyCapabilities
    invites: tuple[LobbyInvite, ...] = ()


# ── Active/completed participant-safe gameplay snapshot ──


class UpdateScenePresenceRequest(ApiModel):
    """Client-reported scene pose; actor identity is always server-derived."""

    x: float = Field(ge=17, le=2383, allow_inf_nan=False)
    y: float = Field(ge=17, le=1583, allow_inf_nan=False)
    facing: Literal["left", "right"]
    moving: StrictBool = False

    @field_validator("x", "y", mode="before")
    @classmethod
    def reject_non_numeric_coordinates(cls, value: object) -> object:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("scene coordinates must be finite numbers")
        return value


class ScenePresencePlayer(ApiModel):
    """Public latest pose for one required room participant."""

    member_id: str
    scene_x: float | None = Field(default=None, ge=17, le=2383, allow_inf_nan=False)
    scene_y: float | None = Field(default=None, ge=17, le=1583, allow_inf_nan=False)
    scene_facing: Literal["left", "right"] | None = None
    scene_moving: bool = False
    scene_online: bool = False

    @model_validator(mode="after")
    def validate_scene_presence(self) -> Self:
        values = (self.scene_x, self.scene_y, self.scene_facing)
        if any(value is None for value in values) and any(value is not None for value in values):
            raise ValueError("scene presence pose must be complete or absent")
        if self.scene_online and any(value is None for value in values):
            raise ValueError("online scene presence requires a complete pose")
        if not self.scene_online and self.scene_moving:
            raise ValueError("offline scene presence cannot be moving")
        return self


class ScenePresenceSnapshotV1(ApiModel):
    """Participant-safe presentation-only pose projection."""

    presence_version: Literal[1] = 1
    session_id: UUID
    self_member_id: str
    players: tuple[ScenePresencePlayer, ...]


class GameplayChapter(ApiModel):
    id: str
    title: str
    content: str


class GameplayMaterial(ApiModel):
    id: str
    kind: Literal["clue", "evidence", "media"]
    title: str
    text: str | None = None
    media_type: str | None = None
    url: str | None = None


class GameplayDiscussionMessage(ApiModel):
    sequence: int = Field(ge=1)
    message_id: UUID
    stage_id: str
    member_id: str
    character_id: str
    text: str


class GameplaySettlementOption(ApiModel):
    id: str
    text: str


class GameplayRevealedBallot(ApiModel):
    member_id: str
    option_id: str


class GameplayRevealedOptionCount(ApiModel):
    option_id: str
    count: int = Field(ge=0)


class GameplaySettlement(ApiModel):
    settlement_id: str
    mode: Literal["secret_vote", "shared_choice", "final_judgment"]
    question: str
    options: tuple[GameplaySettlementOption, ...]
    submitted_member_ids: tuple[str, ...]
    own_option_id: str | None = None
    shared_option_id: str | None = None
    outcome_id: str | None = None
    revealed: bool
    reveal: Literal["named_ballots", "aggregate", "outcome_only"]
    revealed_ballots: tuple[GameplayRevealedBallot, ...] = ()
    revealed_option_counts: tuple[GameplayRevealedOptionCount, ...] = ()


class GameplayHint(ApiModel):
    id: str
    revealed_levels: tuple[str, ...]
    pending_level: int | None = Field(default=None, ge=1, le=3)
    confirming_member_ids: tuple[str, ...] = ()


class GameplayPlayer(ApiModel):
    member_id: str
    character_id: str
    character_name: str
    scene_x: float | None = Field(default=None, ge=17, le=2383, allow_inf_nan=False)
    scene_y: float | None = Field(default=None, ge=17, le=1583, allow_inf_nan=False)
    scene_facing: Literal["left", "right"] | None = None
    scene_moving: bool = False
    scene_online: bool = False

    @model_validator(mode="after")
    def validate_scene_presence(self) -> Self:
        values = (self.scene_x, self.scene_y, self.scene_facing)
        if any(value is None for value in values) and any(value is not None for value in values):
            raise ValueError("scene presence pose must be complete or absent")
        if self.scene_online and any(value is None for value in values):
            raise ValueError("online scene presence requires a complete pose")
        if not self.scene_online and self.scene_moving:
            raise ValueError("offline scene presence cannot be moving")
        return self


class GameplaySnapshotV1(ApiModel):
    snapshot_version: Literal[1] = 1
    session_id: UUID
    mode: Literal["multiplayer_v1"] = "multiplayer_v1"
    status: Literal["active", "completed"]
    revision: int = Field(ge=0)
    event_head_sequence: int = Field(ge=0)
    package: LobbyPackageSummary
    self_member_id: str
    stage_id: str
    stage_name: str
    phase: Literal["read", "discuss", "settle", "reveal"]
    suggested_discussion_minutes: int | None = Field(default=None, gt=0)
    players: tuple[GameplayPlayer, ...]
    read_member_ids: tuple[str, ...]
    discussion_close_member_ids: tuple[str, ...]
    chapters: tuple[GameplayChapter, ...]
    public_materials: tuple[GameplayMaterial, ...]
    discussion_messages: tuple[GameplayDiscussionMessage, ...]
    settlement: GameplaySettlement | None = None
    hints: tuple[GameplayHint, ...] = ()
    can_advance: bool = False
    can_end_incomplete: bool = False
    ending_id: str | None = None

    @model_validator(mode="after")
    def validate_terminal_fields(self) -> Self:
        if (self.status == "completed") != (self.ending_id is not None):
            raise ValueError("completed gameplay snapshots require ending_id")
        return self


class ClosedRoomSnapshotV1(ApiModel):
    session_id: UUID
    mode: Literal["multiplayer_v1"] = "multiplayer_v1"
    status: Literal["closed"] = "closed"
    revision: int = Field(ge=0)
    event_head_sequence: int = Field(ge=0)
    package: LobbyPackageSummary
    self_member_id: str
    closed_at: datetime
    review_available: Literal[False] = False


RoomSnapshotV1: TypeAlias = Annotated[
    LobbySnapshotV1 | GameplaySnapshotV1 | ClosedRoomSnapshotV1,
    Field(discriminator="status"),
]


# Gameplay is parsed by the complete strict union; this alias remains for callers
# that intentionally accept only lobby mutations.
LobbyCommand: TypeAlias = Annotated[
    AssignCharacterCommand | UnassignCharacterCommand | ReadyCommand | StartRoomCommand,
    Field(discriminator="type"),
]

RoomCommand: TypeAlias = MultiplayerCommand


__all__ = [
    "AcceptRoomInviteResponse",
    "CreateAnySessionRequest",
    "CreateAnySessionResponse",
    "CreateMultiplayerSessionRequest",
    "CreateMultiplayerSessionResponse",
    "CreateRoomInviteRequest",
    "ClosedRoomSnapshotV1",
    "CreateRoomInviteResponse",
    "CurrentMultiplayerSession",
    "GameplayChapter",
    "GameplayDiscussionMessage",
    "GameplayHint",
    "GameplayMaterial",
    "GameplayPlayer",
    "GameplayRevealedBallot",
    "GameplayRevealedOptionCount",
    "GameplaySettlement",
    "GameplaySettlementOption",
    "GameplaySnapshotV1",
    "LobbyCapabilities",
    "LobbyCapacity",
    "LobbyCharacter",
    "LobbyCommand",
    "LobbyInvite",
    "LobbyMember",
    "LobbyPackageSummary",
    "LobbySnapshotV1",
    "RoomCommand",
    "RoomSnapshotV1",
    "ScenePresencePlayer",
    "ScenePresenceSnapshotV1",
    "UpdateScenePresenceRequest",
    "CommandResultV1",
]
