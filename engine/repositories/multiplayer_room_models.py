"""定义 MP-2 relational lobby 查询返回的类型化记录。"""

from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID

RoomRole = Literal["host", "player"]
RoomStatus = Literal["lobby", "active"]


@dataclass(frozen=True, slots=True)
class StoredMultiplayerRoom:
    id: UUID
    script_id: str
    status: RoomStatus
    revision: int
    state_schema_version: int
    runtime_package_version: str
    runtime_package_snapshot: dict[str, object]
    runtime_package_sha256: str
    created_at: datetime
    started_at: datetime | None


@dataclass(frozen=True, slots=True)
class StoredRoomMember:
    id: UUID
    session_id: UUID
    principal_id: UUID
    room_role: RoomRole
    ready_at: datetime | None
    joined_at: datetime

    @property
    def ready(self) -> bool:
        return self.ready_at is not None


@dataclass(frozen=True, slots=True)
class StoredRoomAssignment:
    session_id: UUID
    member_id: UUID
    character_id: str
    assigned_at: datetime


@dataclass(frozen=True, slots=True)
class StoredRoomInvite:
    id: UUID
    session_id: UUID
    created_by_member_id: UUID
    token_hash: bytes
    expires_at: datetime
    max_uses: int
    uses_count: int
    revoked_at: datetime | None
    created_at: datetime


@dataclass(frozen=True, slots=True)
class RoomMutationContext:
    room: StoredMultiplayerRoom
    member: StoredRoomMember


# Keep a permissive internal alias for JSONB until the strict snapshot codec validates it.
RuntimePackageSnapshotJson = dict[str, object]
