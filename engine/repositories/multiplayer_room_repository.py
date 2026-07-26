"""Commit-free SQLAlchemy Core persistence for MP-2 multiplayer rooms."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import cast
from uuid import UUID, uuid4

from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import CursorResult, RowMapping
from sqlalchemy.ext.asyncio import AsyncSession

from engine.db.tables import (
    game_sessions,
    room_character_assignments,
    room_invites,
    room_members,
    room_principal_reservations,
    room_required_members,
)
from engine.repositories.multiplayer_room_models import (
    RoomStatus,
    StoredMultiplayerRoom,
    StoredRoomAssignment,
    StoredRoomInvite,
    StoredRoomMember,
)

_ROOM_COLUMNS = (
    game_sessions.c.id,
    game_sessions.c.script_id,
    game_sessions.c.status,
    game_sessions.c.revision,
    game_sessions.c.event_head_sequence,
    game_sessions.c.state_schema_version,
    game_sessions.c.state,
    game_sessions.c.runtime_package_version,
    game_sessions.c.runtime_package_snapshot,
    game_sessions.c.runtime_package_sha256,
    game_sessions.c.created_at,
    game_sessions.c.started_at,
    game_sessions.c.closed_at,
)
_MEMBER_COLUMNS = (
    room_members.c.id,
    room_members.c.session_id,
    room_members.c.principal_id,
    room_members.c.room_role,
    room_members.c.ready_at,
    room_members.c.joined_at,
    room_members.c.scene_x,
    room_members.c.scene_y,
    room_members.c.scene_facing,
    room_members.c.scene_moving,
    room_members.c.scene_updated_at,
)
_ASSIGNMENT_COLUMNS = (
    room_character_assignments.c.session_id,
    room_character_assignments.c.member_id,
    room_character_assignments.c.character_id,
    room_character_assignments.c.assigned_at,
)
_INVITE_COLUMNS = (
    room_invites.c.id,
    room_invites.c.session_id,
    room_invites.c.created_by_member_id,
    room_invites.c.token_hash,
    room_invites.c.expires_at,
    room_invites.c.max_uses,
    room_invites.c.uses_count,
    room_invites.c.revoked_at,
    room_invites.c.created_at,
)


class MultiplayerRoomRepository:
    """Run room statements on one injected request-scoped session without committing."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def advisory_lock(self, session_id: UUID) -> None:
        """Take the room transaction lock on the same connection used by all writes."""

        await self.db.execute(
            select(
                func.pg_advisory_xact_lock(
                    func.hashtextextended(str(session_id), 2),
                )
            )
        )

    async def database_now(self) -> datetime:
        return (await self.db.execute(select(func.now()))).scalar_one()

    async def create_room(
        self,
        *,
        session_id: UUID,
        script_id: str,
        package_version: str,
        package_snapshot: Mapping[str, object],
        package_sha256: str,
    ) -> StoredMultiplayerRoom:
        statement = (
            insert(game_sessions)
            .values(
                id=session_id,
                script_id=script_id,
                player_id=None,
                player_character_id=None,
                state={},
                status="lobby",
                mode="multiplayer_v1",
                revision=0,
                event_head_sequence=0,
                state_schema_version=2,
                runtime_package_version=package_version,
                runtime_package_snapshot=dict(package_snapshot),
                runtime_package_sha256=package_sha256,
                created_at=func.now(),
                updated_at=func.now(),
            )
            .returning(*_ROOM_COLUMNS)
        )
        row = (await self.db.execute(statement)).mappings().one()
        return _room_from_row(row)

    async def lock_room(
        self,
        session_id: UUID,
        *,
        read: bool = False,
    ) -> StoredMultiplayerRoom | None:
        statement = select(*_ROOM_COLUMNS).where(
            game_sessions.c.id == session_id,
            game_sessions.c.mode == "multiplayer_v1",
        )
        statement = statement.with_for_update(read=read)
        row = (await self.db.execute(statement)).mappings().one_or_none()
        return _room_from_row(row) if row is not None else None

    async def get_room(self, session_id: UUID) -> StoredMultiplayerRoom | None:
        """Load a multiplayer room without serializing presentation-only reads or writes."""

        row = (
            (
                await self.db.execute(
                    select(*_ROOM_COLUMNS).where(
                        game_sessions.c.id == session_id,
                        game_sessions.c.mode == "multiplayer_v1",
                    )
                )
            )
            .mappings()
            .one_or_none()
        )
        return _room_from_row(row) if row is not None else None

    async def current_room(self, principal_id: UUID) -> StoredMultiplayerRoom | None:
        statement = (
            select(*_ROOM_COLUMNS)
            .select_from(
                room_principal_reservations.join(
                    game_sessions,
                    game_sessions.c.id == room_principal_reservations.c.session_id,
                )
            )
            .where(
                room_principal_reservations.c.principal_id == principal_id,
                game_sessions.c.mode == "multiplayer_v1",
                game_sessions.c.status.in_(("lobby", "active")),
            )
        )
        row = (await self.db.execute(statement)).mappings().one_or_none()
        return _room_from_row(row) if row is not None else None

    async def create_member(
        self,
        *,
        session_id: UUID,
        principal_id: UUID,
        role: str,
    ) -> StoredRoomMember:
        member_id = uuid4()
        statement = (
            insert(room_members)
            .values(
                id=member_id,
                session_id=session_id,
                principal_id=principal_id,
                room_role=role,
                membership_status="joined",
                ready_at=None,
                joined_at=func.now(),
                left_at=None,
            )
            .returning(*_MEMBER_COLUMNS)
        )
        row = (await self.db.execute(statement)).mappings().one()
        return _member_from_row(row)

    async def reserve_principal(
        self,
        *,
        principal_id: UUID,
        session_id: UUID,
        member_id: UUID,
    ) -> bool:
        statement = (
            pg_insert(room_principal_reservations)
            .values(
                principal_id=principal_id,
                session_id=session_id,
                member_id=member_id,
                created_at=func.now(),
            )
            .on_conflict_do_nothing(index_elements=[room_principal_reservations.c.principal_id])
            .returning(room_principal_reservations.c.principal_id)
        )
        return (await self.db.execute(statement)).scalar_one_or_none() is not None

    async def joined_member(
        self,
        session_id: UUID,
        principal_id: UUID,
    ) -> StoredRoomMember | None:
        row = (
            (
                await self.db.execute(
                    select(*_MEMBER_COLUMNS).where(
                        room_members.c.session_id == session_id,
                        room_members.c.principal_id == principal_id,
                        room_members.c.membership_status == "joined",
                    )
                )
            )
            .mappings()
            .one_or_none()
        )
        return _member_from_row(row) if row is not None else None

    async def joined_members(self, session_id: UUID) -> tuple[StoredRoomMember, ...]:
        rows = (
            (
                await self.db.execute(
                    select(*_MEMBER_COLUMNS)
                    .where(
                        room_members.c.session_id == session_id,
                        room_members.c.membership_status == "joined",
                    )
                    .order_by(room_members.c.joined_at, room_members.c.id)
                )
            )
            .mappings()
            .all()
        )
        return tuple(_member_from_row(row) for row in rows)

    async def update_scene_presence(
        self,
        *,
        session_id: UUID,
        principal_id: UUID,
        x: float,
        y: float,
        facing: str,
        moving: bool,
    ) -> StoredRoomMember | None:
        """Replace only the authenticated joined member's latest non-authoritative pose."""

        row = (
            (
                await self.db.execute(
                    update(room_members)
                    .where(
                        room_members.c.session_id == session_id,
                        room_members.c.principal_id == principal_id,
                        room_members.c.membership_status == "joined",
                    )
                    .values(
                        scene_x=x,
                        scene_y=y,
                        scene_facing=facing,
                        scene_moving=moving,
                        scene_updated_at=func.now(),
                    )
                    .returning(*_MEMBER_COLUMNS)
                )
            )
            .mappings()
            .one_or_none()
        )
        return _member_from_row(row) if row is not None else None

    async def assignments(self, session_id: UUID) -> tuple[StoredRoomAssignment, ...]:
        rows = (
            (
                await self.db.execute(
                    select(*_ASSIGNMENT_COLUMNS)
                    .where(room_character_assignments.c.session_id == session_id)
                    .order_by(
                        room_character_assignments.c.assigned_at,
                        room_character_assignments.c.member_id,
                    )
                )
            )
            .mappings()
            .all()
        )
        return tuple(_assignment_from_row(row) for row in rows)

    async def assignment_for_member(
        self,
        session_id: UUID,
        member_id: UUID,
    ) -> StoredRoomAssignment | None:
        row = (
            (
                await self.db.execute(
                    select(*_ASSIGNMENT_COLUMNS).where(
                        room_character_assignments.c.session_id == session_id,
                        room_character_assignments.c.member_id == member_id,
                    )
                )
            )
            .mappings()
            .one_or_none()
        )
        return _assignment_from_row(row) if row is not None else None

    async def assignment_for_character(
        self,
        session_id: UUID,
        character_id: str,
    ) -> StoredRoomAssignment | None:
        row = (
            (
                await self.db.execute(
                    select(*_ASSIGNMENT_COLUMNS).where(
                        room_character_assignments.c.session_id == session_id,
                        room_character_assignments.c.character_id == character_id,
                    )
                )
            )
            .mappings()
            .one_or_none()
        )
        return _assignment_from_row(row) if row is not None else None

    async def set_assignment(
        self,
        *,
        session_id: UUID,
        member_id: UUID,
        character_id: str,
    ) -> None:
        statement = pg_insert(room_character_assignments).values(
            session_id=session_id,
            member_id=member_id,
            character_id=character_id,
            assigned_at=func.now(),
        )
        await self.db.execute(
            statement.on_conflict_do_update(
                index_elements=[
                    room_character_assignments.c.session_id,
                    room_character_assignments.c.member_id,
                ],
                set_={
                    "character_id": statement.excluded.character_id,
                    "assigned_at": func.now(),
                },
            )
        )
        await self.db.execute(
            update(room_members)
            .where(
                room_members.c.session_id == session_id,
                room_members.c.id == member_id,
            )
            .values(ready_at=None)
        )

    async def remove_assignment(self, session_id: UUID, member_id: UUID) -> bool:
        removed = (
            await self.db.execute(
                delete(room_character_assignments)
                .where(
                    room_character_assignments.c.session_id == session_id,
                    room_character_assignments.c.member_id == member_id,
                )
                .returning(room_character_assignments.c.member_id)
            )
        ).scalar_one_or_none()
        if removed is None:
            return False
        await self.db.execute(
            update(room_members)
            .where(
                room_members.c.session_id == session_id,
                room_members.c.id == member_id,
            )
            .values(ready_at=None)
        )
        return True

    async def set_ready(
        self,
        *,
        session_id: UUID,
        member_id: UUID,
        ready: bool,
    ) -> None:
        await self.db.execute(
            update(room_members)
            .where(
                room_members.c.session_id == session_id,
                room_members.c.id == member_id,
                room_members.c.membership_status == "joined",
            )
            .values(ready_at=func.now() if ready else None)
        )

    async def create_invite(
        self,
        *,
        session_id: UUID,
        creator_member_id: UUID,
        token_hash: bytes,
        expires_at: datetime,
    ) -> StoredRoomInvite | None:
        invite_id = uuid4()
        statement = (
            pg_insert(room_invites)
            .values(
                id=invite_id,
                session_id=session_id,
                created_by_member_id=creator_member_id,
                token_hash=token_hash,
                expires_at=expires_at,
                max_uses=1,
                uses_count=0,
                revoked_at=None,
                created_at=func.now(),
            )
            .on_conflict_do_nothing(index_elements=[room_invites.c.token_hash])
            .returning(*_INVITE_COLUMNS)
        )
        row = (await self.db.execute(statement)).mappings().one_or_none()
        return _invite_from_row(row) if row is not None else None

    async def invite_session_id(self, token_hash: bytes) -> UUID | None:
        value = (
            await self.db.execute(
                select(room_invites.c.session_id).where(room_invites.c.token_hash == token_hash)
            )
        ).scalar_one_or_none()
        return value if isinstance(value, UUID) else None

    async def lock_invite(
        self,
        session_id: UUID,
        *,
        invite_id: UUID | None = None,
        token_hash: bytes | None = None,
    ) -> StoredRoomInvite | None:
        statement = select(*_INVITE_COLUMNS).where(room_invites.c.session_id == session_id)
        if invite_id is not None:
            statement = statement.where(room_invites.c.id == invite_id)
        elif token_hash is not None:
            statement = statement.where(room_invites.c.token_hash == token_hash)
        else:
            raise ValueError("invite_id or token_hash is required")
        row = (await self.db.execute(statement.with_for_update())).mappings().one_or_none()
        return _invite_from_row(row) if row is not None else None

    async def list_invites(self, session_id: UUID) -> tuple[StoredRoomInvite, ...]:
        rows = (
            (
                await self.db.execute(
                    select(*_INVITE_COLUMNS)
                    .where(room_invites.c.session_id == session_id)
                    .order_by(room_invites.c.created_at, room_invites.c.id)
                )
            )
            .mappings()
            .all()
        )
        return tuple(_invite_from_row(row) for row in rows)

    async def revoke_invite(self, invite_id: UUID) -> bool:
        changed = (
            await self.db.execute(
                update(room_invites)
                .where(room_invites.c.id == invite_id, room_invites.c.revoked_at.is_(None))
                .values(revoked_at=func.now())
                .returning(room_invites.c.id)
            )
        ).scalar_one_or_none()
        return changed is not None

    async def consume_invite(self, invite_id: UUID, now: datetime) -> bool:
        changed = (
            await self.db.execute(
                update(room_invites)
                .where(
                    room_invites.c.id == invite_id,
                    room_invites.c.revoked_at.is_(None),
                    room_invites.c.expires_at > now,
                    room_invites.c.uses_count < room_invites.c.max_uses,
                )
                .values(uses_count=room_invites.c.uses_count + 1)
                .returning(room_invites.c.id)
            )
        ).scalar_one_or_none()
        return changed is not None

    async def revoke_all_invites(self, session_id: UUID) -> None:
        await self.db.execute(
            update(room_invites)
            .where(room_invites.c.session_id == session_id, room_invites.c.revoked_at.is_(None))
            .values(revoked_at=func.now())
        )

    async def increment_event_head(self, session_id: UUID) -> int:
        value = (
            await self.db.execute(
                update(game_sessions)
                .where(game_sessions.c.id == session_id)
                .values(
                    event_head_sequence=game_sessions.c.event_head_sequence + 1,
                    updated_at=func.now(),
                )
                .returning(game_sessions.c.event_head_sequence)
            )
        ).scalar_one()
        return int(value)

    async def increment_revision(self, session_id: UUID) -> int:
        value = (
            await self.db.execute(
                update(game_sessions)
                .where(game_sessions.c.id == session_id)
                .values(
                    revision=game_sessions.c.revision + 1,
                    updated_at=func.now(),
                )
                .returning(game_sessions.c.revision)
            )
        ).scalar_one()
        return int(value)

    async def add_required_members(
        self,
        session_id: UUID,
        required: Sequence[tuple[UUID, str]],
    ) -> None:
        if not required:
            return
        await self.db.execute(
            insert(room_required_members),
            [
                {
                    "session_id": session_id,
                    "ordinal": ordinal,
                    "member_id": member_id,
                    "character_id": character_id,
                }
                for ordinal, (member_id, character_id) in enumerate(required)
            ],
        )

    async def replace_game_state(
        self,
        *,
        session_id: UUID,
        state: Mapping[str, object],
        revision: int,
        event_head_sequence: int,
        status: RoomStatus,
    ) -> None:
        result = cast(
            CursorResult[object],
            await self.db.execute(
                update(game_sessions)
                .where(
                    game_sessions.c.id == session_id,
                    game_sessions.c.mode == "multiplayer_v1",
                )
                .values(
                    state=dict(state),
                    status=status,
                    revision=revision,
                    event_head_sequence=event_head_sequence,
                    state_schema_version=2,
                    closed_at=func.now() if status in ("completed", "closed") else None,
                    updated_at=func.now(),
                )
            ),
        )
        if result.rowcount != 1:
            raise MultiplayerRoomStorageError("room.state_update")
        if status in ("completed", "closed"):
            await self.release_reservations(session_id)

    async def release_reservations(self, session_id: UUID) -> None:
        await self.db.execute(
            delete(room_principal_reservations).where(
                room_principal_reservations.c.session_id == session_id
            )
        )

    async def activate_room(
        self,
        *,
        session_id: UUID,
        state: Mapping[str, object],
        revision: int,
    ) -> None:
        await self.db.execute(
            update(game_sessions)
            .where(game_sessions.c.id == session_id)
            .values(
                state=dict(state),
                status="active",
                revision=revision,
                state_schema_version=2,
                started_at=func.now(),
                updated_at=func.now(),
            )
        )


def _room_from_row(row: RowMapping) -> StoredMultiplayerRoom:
    status = str(row["status"])
    if status not in ("lobby", "active", "completed", "closed"):
        raise MultiplayerRoomStorageError("room.status")
    snapshot = _mapping(row["runtime_package_snapshot"])
    state = _mapping(row["state"])
    schema_version = row["state_schema_version"]
    package_version = row["runtime_package_version"]
    package_sha256 = row["runtime_package_sha256"]
    if not isinstance(schema_version, int):
        raise MultiplayerRoomStorageError("room.state_schema_version")
    if not isinstance(package_version, str):
        raise MultiplayerRoomStorageError("room.runtime_package_version")
    if not isinstance(package_sha256, str):
        raise MultiplayerRoomStorageError("room.runtime_package_sha256")
    return StoredMultiplayerRoom(
        id=cast(UUID, row["id"]),
        script_id=str(row["script_id"]),
        status=status,
        revision=int(row["revision"]),
        event_head_sequence=int(row["event_head_sequence"]),
        state_schema_version=schema_version,
        state=state,
        runtime_package_version=package_version,
        runtime_package_snapshot=snapshot,
        runtime_package_sha256=package_sha256,
        created_at=cast(datetime, row["created_at"]),
        started_at=cast(datetime | None, row["started_at"]),
        closed_at=cast(datetime | None, row["closed_at"]),
    )


def _member_from_row(row: RowMapping) -> StoredRoomMember:
    role = str(row["room_role"])
    if role not in ("host", "player"):
        raise MultiplayerRoomStorageError("member.room_role")
    facing = row["scene_facing"]
    if facing not in (None, "left", "right"):
        raise MultiplayerRoomStorageError("member.scene_facing")
    return StoredRoomMember(
        id=cast(UUID, row["id"]),
        session_id=cast(UUID, row["session_id"]),
        principal_id=cast(UUID, row["principal_id"]),
        room_role=role,
        ready_at=cast(datetime | None, row["ready_at"]),
        joined_at=cast(datetime, row["joined_at"]),
        scene_x=float(row["scene_x"]) if row["scene_x"] is not None else None,
        scene_y=float(row["scene_y"]) if row["scene_y"] is not None else None,
        scene_facing=facing,
        scene_moving=cast(bool | None, row["scene_moving"]),
        scene_updated_at=cast(datetime | None, row["scene_updated_at"]),
    )


def _assignment_from_row(row: RowMapping) -> StoredRoomAssignment:
    return StoredRoomAssignment(
        session_id=cast(UUID, row["session_id"]),
        member_id=cast(UUID, row["member_id"]),
        character_id=str(row["character_id"]),
        assigned_at=cast(datetime, row["assigned_at"]),
    )


def _invite_from_row(row: RowMapping) -> StoredRoomInvite:
    return StoredRoomInvite(
        id=cast(UUID, row["id"]),
        session_id=cast(UUID, row["session_id"]),
        created_by_member_id=cast(UUID, row["created_by_member_id"]),
        token_hash=bytes(row["token_hash"]),
        expires_at=cast(datetime, row["expires_at"]),
        max_uses=int(row["max_uses"]),
        uses_count=int(row["uses_count"]),
        revoked_at=cast(datetime | None, row["revoked_at"]),
        created_at=cast(datetime, row["created_at"]),
    )


def _mapping(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise MultiplayerRoomStorageError("json_mapping")
    raw = cast(dict[object, object], value)
    if any(not isinstance(key, str) for key in raw):
        raise MultiplayerRoomStorageError("json_mapping_key")
    return cast(dict[str, object], raw)


class MultiplayerRoomStorageError(ValueError):
    """Report a relational room row that violates the server's storage contract."""
