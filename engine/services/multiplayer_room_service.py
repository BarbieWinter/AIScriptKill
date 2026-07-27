"""Transactional MP-2 multiplayer room orchestration and safe lobby projection."""

from __future__ import annotations

import json
import secrets
from collections.abc import Mapping
from datetime import timedelta
from hashlib import sha256
from typing import Literal, cast
from uuid import UUID, uuid4

from pydantic import JsonValue, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from engine.api.errors import (
    ApiError,
    bad_request,
    conflict,
    forbidden,
    gone,
    not_found,
    unprocessable_entity,
)
from engine.api.middleware.auth import (
    CurrentUser,
    VerifiedAnonymousPrincipal,
    require_verified_anonymous_principal,
)
from engine.api.schemas.multiplayer_rooms import (
    AcceptRoomInviteResponse,
    ClosedRoomSnapshotV1,
    CreateMultiplayerSessionRequest,
    CreateMultiplayerSessionResponse,
    CreateRoomInviteRequest,
    CreateRoomInviteResponse,
    CurrentMultiplayerSession,
    LobbyCapabilities,
    LobbyCapacity,
    LobbyCharacter,
    LobbyInvite,
    LobbyMember,
    LobbyPackageSummary,
    LobbySnapshotV1,
    RoomSnapshotV1,
    UpdateScenePresenceRequest,
)
from engine.contracts.multiplayer_v1.authoring import (
    MULTIPLAYER_STAGE_ADAPTER,
    MultiplayerStageDefinition,
)
from engine.contracts.multiplayer_v1.commands import (
    AssignCharacterCommand,
    CommandResultData,
    CommandResultV1,
    EndIncompleteCommand,
    MultiplayerCommand,
    ReadyCommand,
    StartRoomCommand,
    UnassignCharacterCommand,
)
from engine.contracts.multiplayer_v1.errors import CommandError, MultiplayerErrorCode
from engine.contracts.multiplayer_v1.reviews import CompletedReviewV1
from engine.contracts.multiplayer_v1.state import (
    GAME_STATE_SCHEMA_VERSION,
    GameStateV2,
    PlayerState,
    PrivatePlayerState,
    RoomState,
)
from engine.contracts.multiplayer_v1.vocabulary import CommandStatus, RoomStatus
from engine.core.multiplayer_state_machine import initialize_stage_runtime
from engine.core.package_multiplayer import (
    MULTIPLAYER_STAGE_KEYS,
    first_multiplayer_stage_from_package,
    multiplayer_package_playability,
    multiplayer_policy_from_package,
)
from engine.core.runtime_package_snapshot import (
    RuntimePackageSnapshotError,
    decode_runtime_package_snapshot,
    encode_runtime_package_snapshot,
)
from engine.repositories.multiplayer_room_models import (
    RoomMutationContext,
    StoredMultiplayerRoom,
    StoredRoomAssignment,
    StoredRoomInvite,
    StoredRoomMember,
)
from engine.repositories.multiplayer_room_repository import MultiplayerRoomRepository
from engine.repositories.runtime_package_repository import get_runtime_package
from engine.repositories.session_command_models import (
    canonical_command_payload,
    command_request_sha256,
)
from engine.repositories.session_command_repository import SessionCommandRepository
from engine.services.multiplayer_feature import require_multiplayer_enabled
from engine.services.multiplayer_gameplay_service import (
    apply_gameplay_command,
    decode_room_game_state,
    project_gameplay_snapshot,
    project_multiplayer_review,
)

MAX_MULTIPLAYER_COMMAND_ATTEMPTS = 3


_LOBBY_COMMANDS = (
    AssignCharacterCommand | UnassignCharacterCommand | ReadyCommand | StartRoomCommand
)


async def create_multiplayer_session(
    payload: CreateMultiplayerSessionRequest,
    principal: VerifiedAnonymousPrincipal,
    db: AsyncSession,
) -> CreateMultiplayerSessionResponse:
    """Freeze a published package and atomically create the host room reservation."""

    require_multiplayer_enabled()
    repository = MultiplayerRoomRepository(db)
    session_id = uuid4()
    await repository.advisory_lock(session_id)
    package = await get_runtime_package(db, payload.script_id, lock_existing=True)
    if package is None:
        raise not_found("SCRIPT_PACKAGE_NOT_FOUND", "未找到可用于多人房间的已发布剧本包")
    playability = multiplayer_package_playability(package)
    if not playability.playable:
        diagnostic = playability.diagnostics[0]
        raise unprocessable_entity(
            "PACKAGE_NOT_MULTIPLAYER",
            diagnostic.message,
            diagnostic.details(),
        )
    try:
        snapshot = encode_runtime_package_snapshot(package)
    except RuntimePackageSnapshotError as exc:
        raise unprocessable_entity(
            "PACKAGE_NOT_MULTIPLAYER",
            "剧本包无法生成固定运行快照",
        ) from exc

    room = await repository.create_room(
        session_id=session_id,
        script_id=payload.script_id,
        package_version=package.package.version,
        package_snapshot=snapshot.payload,
        package_sha256=snapshot.sha256,
    )
    member = await repository.create_member(
        session_id=room.id,
        principal_id=principal.id,
        role="host",
    )
    reserved = await repository.reserve_principal(
        principal_id=principal.id,
        session_id=room.id,
        member_id=member.id,
    )
    if not reserved:
        current = await repository.current_room(principal.id)
        details = {"session_id": str(current.id)} if current is not None else None
        raise conflict(
            "UNFINISHED_ROOM_EXISTS",
            "当前身份已经加入一个未完成的多人房间",
            details,
        )
    await db.commit()
    return CreateMultiplayerSessionResponse(
        session_id=room.id,
        revision=room.revision,
        member_id=member.id,
        created_at=room.created_at,
    )


async def get_current_multiplayer_session(
    principal: VerifiedAnonymousPrincipal,
    db: AsyncSession,
) -> CurrentMultiplayerSession | None:
    require_multiplayer_enabled()
    room = await MultiplayerRoomRepository(db).current_room(principal.id)
    if room is None:
        return None
    if room.status not in ("lobby", "active"):
        raise conflict("ROOM_STATE_INVALID", "当前房间状态不属于未完成多人房间")
    return CurrentMultiplayerSession(session_id=room.id, status=room.status)


async def create_room_invite(
    session_id: str,
    payload: CreateRoomInviteRequest,
    principal: VerifiedAnonymousPrincipal,
    db: AsyncSession,
) -> CreateRoomInviteResponse:
    require_multiplayer_enabled()
    repository = MultiplayerRoomRepository(db)
    context = await _lock_mutation(repository, session_id, principal.id)
    _require_lobby(context.room)
    _require_host(context.member)
    members = await repository.joined_members(context.room.id)
    package = _decode_room_package(context.room)
    policy = multiplayer_policy_from_package(package)
    if len(members) >= policy.max_players:
        raise conflict("ROOM_FULL", "房间人数已满")

    now = await repository.database_now()
    expires_at = now + timedelta(seconds=payload.ttl_seconds)
    invite = None
    token = ""
    for _ in range(3):
        token = secrets.token_urlsafe(32)
        invite = await repository.create_invite(
            session_id=context.room.id,
            creator_member_id=context.member.id,
            token_hash=_invite_digest(token),
            expires_at=expires_at,
        )
        if invite is not None:
            break
    if invite is None:
        raise conflict("INVITE_TOKEN_COLLISION", "无法生成唯一邀请，请重试")
    await repository.increment_revision(context.room.id)
    await db.commit()
    return CreateRoomInviteResponse(
        invite_id=invite.id,
        token=token,
        expires_at=invite.expires_at,
    )


async def revoke_room_invite(
    session_id: str,
    invite_id: str,
    principal: VerifiedAnonymousPrincipal,
    db: AsyncSession,
) -> None:
    require_multiplayer_enabled()
    repository = MultiplayerRoomRepository(db)
    context = await _lock_mutation(repository, session_id, principal.id)
    _require_lobby(context.room)
    _require_host(context.member)
    parsed_invite_id = _uuid(invite_id, "INVALID_INVITE_ID", "invite_id 必须是 UUID")
    invite = await repository.lock_invite(context.room.id, invite_id=parsed_invite_id)
    if invite is None:
        raise not_found("INVITE_NOT_FOUND", "未找到指定房间邀请")
    if await repository.revoke_invite(invite.id):
        await repository.increment_revision(context.room.id)
    await db.commit()


async def accept_room_invite(
    token: str,
    principal: VerifiedAnonymousPrincipal,
    db: AsyncSession,
) -> AcceptRoomInviteResponse:
    require_multiplayer_enabled()
    repository = MultiplayerRoomRepository(db)
    token_hash = _invite_digest(token)
    session_id = await repository.invite_session_id(token_hash)
    if session_id is None:
        raise not_found("INVITE_NOT_FOUND", "邀请不存在")

    await repository.advisory_lock(session_id)
    room = await repository.lock_room(session_id)
    if room is None:
        raise not_found("INVITE_NOT_FOUND", "邀请不存在")
    _require_lobby(room)
    invite = await repository.lock_invite(session_id, token_hash=token_hash)
    if invite is None:
        raise not_found("INVITE_NOT_FOUND", "邀请不存在")

    existing = await repository.joined_member(session_id, principal.id)
    if existing is not None:
        await db.commit()
        return AcceptRoomInviteResponse(
            session_id=session_id,
            revision=room.revision,
            member_id=existing.id,
        )

    now = await repository.database_now()
    if invite.revoked_at is not None:
        raise gone("INVITE_REVOKED", "邀请已撤销")
    if invite.expires_at <= now:
        raise gone("INVITE_EXPIRED", "邀请已过期")
    if invite.uses_count >= invite.max_uses:
        raise conflict("INVITE_EXHAUSTED", "邀请已被使用")

    package = _decode_room_package(room)
    policy = multiplayer_policy_from_package(package)
    members = await repository.joined_members(session_id)
    if len(members) >= policy.max_players:
        raise conflict("ROOM_FULL", "房间人数已满")

    member = await repository.create_member(
        session_id=session_id,
        principal_id=principal.id,
        role="player",
    )
    reserved = await repository.reserve_principal(
        principal_id=principal.id,
        session_id=session_id,
        member_id=member.id,
    )
    if not reserved:
        current = await repository.current_room(principal.id)
        details = {"session_id": str(current.id)} if current is not None else None
        raise conflict(
            "UNFINISHED_ROOM_EXISTS",
            "当前身份已经加入一个未完成的多人房间",
            details,
        )
    if not await repository.consume_invite(invite.id, now):
        raise conflict("INVITE_EXHAUSTED", "邀请已被使用")
    revision = await repository.increment_revision(session_id)
    await db.commit()
    return AcceptRoomInviteResponse(
        session_id=session_id,
        revision=revision,
        member_id=member.id,
    )


async def get_room_snapshot(
    session_id: str,
    principal: VerifiedAnonymousPrincipal,
    db: AsyncSession,
) -> RoomSnapshotV1:
    """Return a status-aware participant-safe lobby or gameplay snapshot."""

    require_multiplayer_enabled()
    repository = MultiplayerRoomRepository(db)
    room_id = _uuid(session_id, "INVALID_SESSION_ID", "session_id 必须是 UUID")
    room = await repository.lock_room(room_id, read=True)
    if room is None:
        raise not_found("SESSION_NOT_FOUND", "未找到指定多人房间")
    member = await repository.joined_member(room.id, principal.id)
    if member is None:
        raise forbidden("NOT_ROOM_MEMBER", "当前身份不是房间成员")
    if room.status == "lobby":
        members = await repository.joined_members(room.id)
        assignments = await repository.assignments(room.id)
        invites = await repository.list_invites(room.id) if member.room_role == "host" else ()
        return _lobby_snapshot(room, member, members, assignments, invites)
    if room.status in ("active", "completed"):
        package = _decode_room_package(room)
        rows = await SessionCommandRepository(db).list_events(
            room.id,
            0,
            max(room.event_head_sequence, 1),
        )
        members = await repository.joined_members(room.id)
        presence_now = await repository.database_now()
        return project_gameplay_snapshot(
            room=room,
            member=member,
            members=members,
            presence_now=presence_now,
            package=package,
            event_rows=rows,
        )
    if room.status == "closed":
        return _closed_snapshot(room, member)
    raise conflict("ROOM_STATE_INVALID", "多人房间生命周期状态无效")


async def update_scene_presence(
    session_id: str,
    payload: UpdateScenePresenceRequest,
    principal: VerifiedAnonymousPrincipal,
    db: AsyncSession,
) -> None:
    """Replace the authenticated active member's latest presentation-only pose."""

    require_multiplayer_enabled()
    repository = MultiplayerRoomRepository(db)
    room_id = _uuid(session_id, "INVALID_SESSION_ID", "session_id 必须是 UUID")
    await repository.advisory_lock(room_id)
    room = await repository.lock_room(room_id)
    if room is None:
        raise not_found("SESSION_NOT_FOUND", "未找到指定多人房间")
    member = await repository.joined_member(room.id, principal.id)
    if member is None:
        raise forbidden("NOT_ROOM_MEMBER", "当前身份不是房间成员")
    _require_active(room)
    state = decode_room_game_state(room)
    if str(member.id) not in state.room.required_member_ids:
        raise forbidden("NOT_ROOM_MEMBER", "当前身份不是已开始房间的参与者")
    updated = await repository.update_scene_presence(
        session_id=room.id,
        principal_id=principal.id,
        x=payload.x,
        y=payload.y,
        facing=payload.facing,
        moving=payload.moving,
    )
    if updated is None:
        raise forbidden("NOT_ROOM_MEMBER", "当前身份不是房间成员")
    await db.commit()


async def get_lobby_snapshot(
    session_id: str,
    principal: VerifiedAnonymousPrincipal,
    db: AsyncSession,
) -> RoomSnapshotV1:
    """Compatibility entry point for callers predating gameplay snapshots."""

    return await get_room_snapshot(session_id, principal, db)


async def get_multiplayer_review_if_present(
    session_id: str,
    current_user: CurrentUser,
    db: AsyncSession,
) -> CompletedReviewV1 | None:
    """Project a multiplayer review, or return None for a legacy session ID."""

    room_id = _uuid(session_id, "INVALID_SESSION_ID", "session_id 必须是 UUID")
    repository = MultiplayerRoomRepository(db)
    room = await repository.lock_room(room_id, read=True)
    if room is None:
        return None
    require_multiplayer_enabled()
    principal = await require_verified_anonymous_principal(current_user)
    member = await repository.joined_member(room.id, principal.id)
    if member is None:
        raise forbidden("NOT_ROOM_MEMBER", "当前身份不是房间成员")
    if room.status != "completed":
        raise conflict("REVIEW_NOT_AVAILABLE", "多人游戏完成后才能查看复盘")
    return project_multiplayer_review(
        room=room,
        member=member,
        package=_decode_room_package(room),
    )


async def execute_room_command(
    session_id: str,
    command: MultiplayerCommand,
    principal: VerifiedAnonymousPrincipal,
    db: AsyncSession,
) -> CommandResultV1:
    require_multiplayer_enabled()
    repository = MultiplayerRoomRepository(db)
    context = await _lock_mutation(repository, session_id, principal.id)
    receipts = SessionCommandRepository(db)
    command_identity = await receipts.get_command_identity(command.command_id)
    if command_identity is not None and command_identity["session_id"] != context.room.id:
        raise conflict("COMMAND_ID_REUSED", "command_id 已绑定到其他多人房间")
    request_hash = command_request_sha256(command)
    existing = await receipts.get_receipt(context.room.id, command.command_id)
    claim_committed = False
    if existing is not None:
        _require_receipt_actor(existing, context)
        if existing.request_sha256 != request_hash:
            raise conflict("COMMAND_ID_REUSED", "command_id 已绑定到不同的多人命令")
        if existing.status == "processing":
            if existing.attempt_count >= MAX_MULTIPLAYER_COMMAND_ATTEMPTS:
                failed = await receipts.fail_expired_receipt(
                    context.room.id,
                    command.command_id,
                    existing.attempt_count,
                    {"attempt_count": existing.attempt_count},
                )
                if not failed:
                    raise conflict("COMMAND_IN_PROGRESS", "该 command_id 已被另一个恢复进程领取")
                await db.commit()
                raise conflict("COMMAND_RECOVERY_EXHAUSTED", "该 command_id 已超过恢复次数上限")
            reclaimed = await receipts.reclaim_expired_receipt(
                context.room.id,
                command.command_id,
                existing.attempt_count,
            )
            if reclaimed is None:
                raise conflict("COMMAND_IN_PROGRESS", "该 command_id 已被另一个恢复进程领取")
            existing = reclaimed
            await db.commit()
            claim_committed = True
        else:
            if existing.status == "succeeded" and isinstance(existing.result, dict):
                stored_result = existing.result
            elif existing.status == "rejected":
                candidate = existing.error_details.get("command_result")
                if not isinstance(candidate, dict):
                    raise conflict("COMMAND_RECEIPT_INVALID", "多人命令 receipt 无法重放")
                stored_result = cast(dict[str, object], candidate)
            elif existing.status == "failed":
                if existing.error_code == "COMMAND_SUPERSEDED":
                    raise conflict("COMMAND_SUPERSEDED", "该 command_id 已被后续命令取代")
                raise conflict("COMMAND_RECOVERY_EXHAUSTED", "该 command_id 已超过恢复次数上限")
            else:
                raise conflict("COMMAND_RECEIPT_INVALID", "多人命令 receipt 无法重放")
            return CommandResultV1.model_validate_json(
                json.dumps({**stored_result, "replayed": True})
            )

    claimed = existing
    if claimed is None:
        blocker = await receipts.get_active_processing_receipt(context.room.id)
        if blocker is not None:
            failed = await receipts.fail_expired_receipt(
                context.room.id,
                blocker.command_id,
                blocker.attempt_count,
                {
                    "attempt_count": blocker.attempt_count,
                    "reason": "superseded_by_new_command",
                },
                error_code="COMMAND_SUPERSEDED",
            )
            if not failed:
                raise conflict("COMMAND_IN_PROGRESS", "该房间已有命令正在处理中")
        claimed = await receipts.claim_receipt(
            session_id=context.room.id,
            command_id=command.command_id,
            request_payload=canonical_command_payload(command),
            request_sha256=request_hash,
            expected_revision=command.expected_revision,
            base_revision=context.room.revision,
            actor_principal_id=principal.id,
            actor_member_id=context.member.id,
            command_kind="multiplayer_v1",
        )
    if claimed is None:
        command_identity = await receipts.get_command_identity(command.command_id)
        if command_identity is not None and command_identity["session_id"] != context.room.id:
            raise conflict("COMMAND_ID_REUSED", "command_id 已绑定到其他多人房间")
        raise conflict("COMMAND_IN_PROGRESS", "该房间已有命令正在处理中")
    if existing is None:
        await db.commit()
        claim_committed = True

    if not claim_committed:
        raise RuntimeError("multiplayer command claim must be committed before execution")
    context = await _lock_mutation(repository, session_id, principal.id)

    try:
        if context.room.status == "closed":
            raise conflict("ROOM_CLOSED", "多人房间已经关闭")
        if isinstance(command, EndIncompleteCommand):
            if context.room.status == "completed":
                raise conflict("ROOM_ALREADY_COMPLETED", "已完成房间不能改为未完成关闭")
            _require_host(context.member)
        elif isinstance(command, _LOBBY_COMMANDS):
            _require_lobby(context.room)
        else:
            _require_active(context.room)
    except ApiError as exc:
        await db.rollback()
        return await _reject_room_command(
            receipts,
            context,
            command,
            exc,
            claimed.attempt_count,
            db,
        )
    if command.expected_revision != context.room.revision:
        if not claim_committed:
            raise RuntimeError("multiplayer command claim must be committed before execution")
        details = {
            "expected_revision": str(command.expected_revision),
            "actual_revision": str(context.room.revision),
        }
        result = CommandResultV1(
            command_id=command.command_id,
            status=CommandStatus.REJECTED,
            revision=context.room.revision,
            event_sequence=0,
            error=CommandError(
                code=MultiplayerErrorCode.REVISION_MISMATCH,
                message="房间 revision 已变化，请刷新快照",
                details=cast(dict[str, JsonValue], details),
            ),
            replayed=False,
        )
        rejected = await receipts.reject_receipt(
            context.room.id,
            command.command_id,
            "REVISION_MISMATCH",
            {**details, "command_result": result.model_dump(mode="json")},
            attempt_count=claimed.attempt_count,
        )
        if not rejected:
            await db.rollback()
            raise conflict("COMMAND_ATTEMPT_FENCED", "该 command attempt 已失去执行权")
        await db.commit()
        return result

    if not claim_committed:
        raise RuntimeError("multiplayer command claim must be committed before execution")
    try:
        event_type = "lobby.command_succeeded"
        event_payload: dict[str, object] = {"command_type": command.type}
        event_required = False
        outbox_topic: str | None = "room.events.v1"
        if isinstance(command, EndIncompleteCommand):
            previous_status = context.room.status
            revision = await _close_incomplete_room(repository, context)
            event_required = True
            event_type = "room.incomplete_closed"
            event_payload = {
                "command_type": command.type,
                "previous_status": previous_status,
            }
        elif isinstance(command, AssignCharacterCommand):
            revision = await _assign_character(repository, context, command.payload.character_id)
            event_required = revision != context.room.revision
        elif isinstance(command, UnassignCharacterCommand):
            revision = await _unassign_character(repository, context)
            event_required = revision != context.room.revision
        elif isinstance(command, ReadyCommand):
            revision = await _set_ready(repository, context, command.payload.ready)
            event_required = revision != context.room.revision
        elif isinstance(command, StartRoomCommand):
            revision = await _start_room(repository, context)
            event_required = revision != context.room.revision
        else:
            package = _decode_room_package(context.room)
            mutation = apply_gameplay_command(
                room=context.room,
                member=context.member,
                command=command,
                package=package,
            )
            revision = (
                context.room.revision + 1 if mutation.state_changed else context.room.revision
            )
            event_required = mutation.event_required
            event_type = mutation.event_type
            event_payload = mutation.event_payload
            outbox_topic = None
            next_sequence = (
                context.room.event_head_sequence + 1
                if event_required
                else context.room.event_head_sequence
            )
            if mutation.state_changed:
                next_state = mutation.state.model_copy(update={"room_revision": revision})
                next_state = GameStateV2.model_validate(next_state.model_dump())
                await repository.replace_game_state(
                    session_id=context.room.id,
                    state=next_state.model_dump(mode="json"),
                    revision=revision,
                    event_head_sequence=next_sequence,
                    status=cast(
                        Literal["active", "completed"],
                        next_state.room.status.value,
                    ),
                )
            elif event_required:
                persisted_sequence = await repository.increment_event_head(context.room.id)
                if persisted_sequence != next_sequence:
                    raise RuntimeError("room event head advanced unexpectedly")
    except ApiError as exc:
        await db.rollback()
        return await _reject_room_command(
            receipts,
            context,
            command,
            exc,
            claimed.attempt_count,
            db,
        )

    is_gameplay = not isinstance(command, _LOBBY_COMMANDS)
    if is_gameplay:
        event_sequence = context.room.event_head_sequence + 1 if event_required else 0
    else:
        event_sequence = (
            await repository.increment_event_head(context.room.id) if event_required else 0
        )
    result = CommandResultV1(
        command_id=command.command_id,
        status=CommandStatus.ACCEPTED,
        revision=revision,
        event_sequence=event_sequence,
        result=CommandResultData(),
        replayed=False,
    )
    result_payload = result.model_dump(mode="json")
    finalized = await receipts.finalize_success(
        session_id=context.room.id,
        command_id=command.command_id,
        result=result_payload,
        revision=revision,
        event_sequence=event_sequence if event_required else None,
        event_type=event_type,
        event_payload=event_payload,
        attempt_count=claimed.attempt_count,
        outbox_topic=outbox_topic,
    )
    if not finalized:
        await db.rollback()
        await receipts.expire_lease(
            context.room.id,
            command.command_id,
            claimed.attempt_count,
        )
        await db.commit()
        raise conflict("COMMAND_ATTEMPT_FENCED", "该 command attempt 已失去执行权")
    await db.commit()
    return result


async def execute_lobby_command(
    session_id: str,
    command: MultiplayerCommand,
    principal: VerifiedAnonymousPrincipal,
    db: AsyncSession,
) -> CommandResultV1:
    """Compatibility wrapper that intentionally accepts lobby commands only."""

    if not isinstance(command, _LOBBY_COMMANDS):
        raise unprocessable_entity(
            "COMMAND_NOT_AVAILABLE",
            "该命令不属于 MP-2 房间大厅能力",
        )
    return await execute_room_command(session_id, command, principal, db)


def _require_receipt_actor(
    receipt: object,
    context: RoomMutationContext,
) -> None:
    principal_id = getattr(receipt, "actor_principal_id", None)
    member_id = getattr(receipt, "actor_member_id", None)
    if principal_id != context.member.principal_id or member_id != context.member.id:
        raise not_found("COMMAND_NOT_FOUND", "未找到指定 command receipt")


async def _reject_room_command(
    receipts: SessionCommandRepository,
    context: RoomMutationContext,
    command: MultiplayerCommand,
    error: ApiError,
    attempt_count: int,
    db: AsyncSession,
) -> CommandResultV1:
    try:
        error_code = MultiplayerErrorCode(error.error.code)
    except ValueError:
        error_code = MultiplayerErrorCode.INVALID_COMMAND
    result = CommandResultV1(
        command_id=command.command_id,
        status=CommandStatus.REJECTED,
        revision=context.room.revision,
        event_sequence=0,
        error=CommandError(
            code=error_code,
            message=error.error.message,
            details=error.error.details,
        ),
        replayed=False,
    )
    rejected = await receipts.reject_receipt(
        context.room.id,
        command.command_id,
        error.error.code,
        {"command_result": result.model_dump(mode="json")},
        attempt_count=attempt_count,
    )
    if not rejected:
        await db.rollback()
        raise conflict("COMMAND_ATTEMPT_FENCED", "该 command attempt 已失去执行权")
    await db.commit()
    return result


async def _assign_character(
    repository: MultiplayerRoomRepository,
    context: RoomMutationContext,
    character_id: str,
) -> int:
    package = _decode_room_package(context.room)
    policy = multiplayer_policy_from_package(package)
    if character_id not in policy.playable_character_ids:
        raise unprocessable_entity("CHARACTER_NOT_PLAYABLE", "指定角色不可供玩家选择")
    current = await repository.assignment_for_member(context.room.id, context.member.id)
    if current is not None and current.character_id == character_id:
        return context.room.revision
    holder = await repository.assignment_for_character(context.room.id, character_id)
    if holder is not None and holder.member_id != context.member.id:
        raise conflict("CHARACTER_ALREADY_ASSIGNED", "指定角色已被其他成员选择")
    await repository.set_assignment(
        session_id=context.room.id,
        member_id=context.member.id,
        character_id=character_id,
    )
    return await repository.increment_revision(context.room.id)


async def _unassign_character(
    repository: MultiplayerRoomRepository,
    context: RoomMutationContext,
) -> int:
    if not await repository.remove_assignment(context.room.id, context.member.id):
        return context.room.revision
    return await repository.increment_revision(context.room.id)


async def _set_ready(
    repository: MultiplayerRoomRepository,
    context: RoomMutationContext,
    ready: bool,
) -> int:
    if context.member.ready == ready:
        return context.room.revision
    if ready and await repository.assignment_for_member(context.room.id, context.member.id) is None:
        raise conflict("CHARACTER_REQUIRED", "准备前必须先选择角色")
    await repository.set_ready(
        session_id=context.room.id,
        member_id=context.member.id,
        ready=ready,
    )
    return await repository.increment_revision(context.room.id)


async def _close_incomplete_room(
    repository: MultiplayerRoomRepository,
    context: RoomMutationContext,
) -> int:
    next_revision = context.room.revision + 1
    next_sequence = context.room.event_head_sequence + 1
    state: Mapping[str, object] = context.room.state
    if context.room.status == "active":
        current = decode_room_game_state(context.room)
        closed_room = current.room.model_copy(update={"status": RoomStatus.CLOSED})
        closed = current.model_copy(
            update={
                "room": closed_room,
                "room_revision": next_revision,
            }
        )
        state = GameStateV2.model_validate(closed.model_dump()).model_dump(mode="json")
    await repository.close_incomplete_room(
        session_id=context.room.id,
        state=state,
        revision=next_revision,
        event_head_sequence=next_sequence,
    )
    return next_revision


async def _start_room(
    repository: MultiplayerRoomRepository,
    context: RoomMutationContext,
) -> int:
    _require_host(context.member)
    package = _decode_room_package(context.room)
    policy = multiplayer_policy_from_package(package)
    members = await repository.joined_members(context.room.id)
    if len(members) != policy.max_players:
        raise conflict("ROOM_NOT_FULL", "房间必须恰好包含两名成员才能开始")
    assignments = await repository.assignments(context.room.id)
    assignment_by_member = {item.member_id: item.character_id for item in assignments}
    if set(assignment_by_member) != {member.id for member in members}:
        raise conflict("ASSIGNMENTS_INCOMPLETE", "所有成员都必须选择角色")
    if len(set(assignment_by_member.values())) != len(members):
        raise conflict("ASSIGNMENTS_INCOMPLETE", "成员角色分配必须唯一")
    if any(not member.ready for member in members):
        raise conflict("PLAYERS_NOT_READY", "所有成员都必须准备完成")

    stage_record = first_multiplayer_stage_from_package(package)
    definition = _stage_definition(stage_record.id, stage_record.definition)
    required_member_ids = tuple(str(member.id) for member in members)
    next_revision = context.room.revision + 1
    players: dict[str, PlayerState] = {}
    private_by_member: dict[str, PrivatePlayerState] = {}
    required_rows: list[tuple[UUID, str]] = []
    chapters_by_id = {chapter.id: chapter for chapter in package.chapters}
    for member in members:
        member_id = str(member.id)
        character_id = assignment_by_member[member.id]
        chapter_id = definition.chapters.get(character_id)
        chapter = chapters_by_id.get(chapter_id or "")
        if chapter is None or chapter.character_id != character_id:
            raise conflict("ROOM_PACKAGE_INVALID", "固定剧本包的首阶段角色章节无效")
        players[member_id] = PlayerState(
            member_id=member_id,
            character_id=character_id,
            ready=True,
        )
        private_by_member[member_id] = PrivatePlayerState(
            character_id=character_id,
            unlocked_chapter_ids=(chapter.id,),
        )
        required_rows.append((member.id, character_id))

    state = GameStateV2(
        state_schema_version=GAME_STATE_SCHEMA_VERSION,
        session_id=context.room.id,
        room_revision=next_revision,
        room=RoomState(
            status=RoomStatus.ACTIVE,
            required_member_ids=required_member_ids,
            current_stage_id=definition.id,
        ),
        players=players,
        private_by_member=private_by_member,
        stage=initialize_stage_runtime(
            definition,
            required_member_ids=required_member_ids,
        ),
    )
    await repository.add_required_members(context.room.id, required_rows)
    await repository.activate_room(
        session_id=context.room.id,
        state=state.model_dump(mode="json"),
        revision=next_revision,
    )
    await repository.revoke_all_invites(context.room.id)
    return next_revision


async def _lock_mutation(
    repository: MultiplayerRoomRepository,
    session_id: str,
    principal_id: UUID,
) -> RoomMutationContext:
    room_id = _uuid(session_id, "INVALID_SESSION_ID", "session_id 必须是 UUID")
    await repository.advisory_lock(room_id)
    room = await repository.lock_room(room_id)
    if room is None:
        raise not_found("SESSION_NOT_FOUND", "未找到指定多人房间")
    member = await repository.joined_member(room_id, principal_id)
    if member is None:
        raise forbidden("NOT_ROOM_MEMBER", "当前身份不是房间成员")
    return RoomMutationContext(room=room, member=member)


def _character_public_description(definition: Mapping[str, JsonValue]) -> str:
    identity = definition.get("identity")
    if isinstance(identity, dict):
        public_description = identity.get("public")
        if isinstance(public_description, str) and public_description.strip():
            return public_description.strip()
    return "该角色的公开身份将在游戏开始后用于协作。"


def _lobby_snapshot(
    room: StoredMultiplayerRoom,
    self_member: StoredRoomMember,
    members: tuple[StoredRoomMember, ...],
    assignments: tuple[StoredRoomAssignment, ...],
    invites: tuple[StoredRoomInvite, ...],
) -> LobbySnapshotV1:
    package = _decode_room_package(room)
    policy = multiplayer_policy_from_package(package)
    assignment_by_member = {item.member_id: item.character_id for item in assignments}
    member_by_character = {item.character_id: item.member_id for item in assignments}
    member_models = tuple(
        LobbyMember(
            member_id=member.id,
            room_role=member.room_role,
            character_id=assignment_by_member.get(member.id),
            ready=member.ready,
        )
        for member in members
    )
    self_model = next(item for item in member_models if item.member_id == self_member.id)
    joined = len(members)
    complete_assignments = len(assignment_by_member) == joined
    all_ready = bool(members) and all(member.ready for member in members)
    can_start = (
        room.status == "lobby"
        and self_member.room_role == "host"
        and joined == policy.max_players
        and complete_assignments
        and all_ready
    )

    # The concrete invite type is intentionally consumed only through safe metadata fields.
    safe_invites = tuple(
        LobbyInvite(
            invite_id=invite.id,
            expires_at=invite.expires_at,
            uses_count=invite.uses_count,
            max_uses=invite.max_uses,
            revoked=invite.revoked_at is not None,
        )
        for invite in invites
    )
    return LobbySnapshotV1(
        session_id=room.id,
        status="lobby",
        revision=room.revision,
        package=LobbyPackageSummary(
            script_id=package.package.id,
            title=package.package.title,
            version=package.package.version,
        ),
        capacity=LobbyCapacity(
            min_players=policy.min_players,
            max_players=policy.max_players,
            joined=joined,
        ),
        self=self_model,
        members=member_models,
        characters=tuple(
            LobbyCharacter(
                id=character.id,
                name=character.name,
                public_description=_character_public_description(character.definition),
                assigned_member_id=member_by_character.get(character.id),
            )
            for character in sorted(package.characters, key=lambda item: (item.sort_order, item.id))
            if character.id in policy.playable_character_ids
        ),
        capabilities=LobbyCapabilities(
            can_invite=(
                room.status == "lobby"
                and self_member.room_role == "host"
                and joined < policy.max_players
            ),
            can_assign_character=room.status == "lobby",
            can_ready=(room.status == "lobby" and self_member.id in assignment_by_member),
            can_start=can_start,
            can_end_incomplete=(room.status == "lobby" and self_member.room_role == "host"),
        ),
        invites=safe_invites,
    )


def _closed_snapshot(
    room: StoredMultiplayerRoom,
    member: StoredRoomMember,
) -> ClosedRoomSnapshotV1:
    if room.closed_at is None:
        raise conflict("ROOM_STATE_INVALID", "已关闭多人房间缺少关闭时间")
    package = _decode_room_package(room)
    return ClosedRoomSnapshotV1(
        session_id=room.id,
        revision=room.revision,
        event_head_sequence=room.event_head_sequence,
        package=LobbyPackageSummary(
            script_id=package.package.id,
            title=package.package.title,
            version=package.package.version,
        ),
        self_member_id=str(member.id),
        closed_at=room.closed_at,
    )


def _decode_room_package(room: StoredMultiplayerRoom):
    try:
        package = decode_runtime_package_snapshot(
            room.runtime_package_snapshot,
            room.runtime_package_sha256,
            expected_package_id=room.script_id,
            expected_package_version=room.runtime_package_version,
        )
    except RuntimePackageSnapshotError as exc:
        raise conflict("ROOM_PACKAGE_INVALID", "房间固定剧本包校验失败") from exc
    playability = multiplayer_package_playability(package)
    if not playability.playable:
        diagnostic = playability.diagnostics[0]
        raise conflict(
            "ROOM_PACKAGE_INVALID",
            diagnostic.message,
            diagnostic.details(),
        )
    return package


def _stage_definition(stage_id: str, raw: Mapping[str, object]) -> MultiplayerStageDefinition:
    selected: dict[str, object] = {"id": stage_id}
    for key in MULTIPLAYER_STAGE_KEYS:
        selected[key] = raw.get(key)
    try:
        return MULTIPLAYER_STAGE_ADAPTER.validate_json(
            json.dumps(selected, ensure_ascii=False, allow_nan=False)
        )
    except (ValidationError, ValueError, TypeError) as exc:
        raise conflict("ROOM_PACKAGE_INVALID", "房间固定剧本包的首阶段定义无效") from exc


def _require_lobby(room: StoredMultiplayerRoom) -> None:
    if room.status != "lobby":
        raise conflict("ROOM_NOT_IN_LOBBY", "房间不再处于大厅状态")


def _require_active(room: StoredMultiplayerRoom) -> None:
    if room.status != "active":
        raise conflict("ROOM_NOT_ACTIVE", "房间不再处于游戏中")


def _require_host(member: StoredRoomMember) -> None:
    if member.room_role != "host":
        raise forbidden("HOST_REQUIRED", "该操作仅房主可执行")


def _uuid(value: str, code: str, message: str) -> UUID:
    try:
        return UUID(value)
    except ValueError as exc:
        raise bad_request(code, message) from exc


def _invite_digest(token: str) -> bytes:
    return sha256(token.encode("utf-8")).digest()
