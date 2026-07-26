"""Apply and project the minimal HTTP-polling Multiplayer v1 game flow."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal, cast
from uuid import UUID

from pydantic import ValidationError

from engine.api.errors import conflict, unprocessable_entity
from engine.api.schemas.multiplayer_rooms import (
    GameplayChapter,
    GameplayDiscussionMessage,
    GameplayHint,
    GameplayMaterial,
    GameplayPlayer,
    GameplayRevealedBallot,
    GameplayRevealedOptionCount,
    GameplaySettlement,
    GameplaySettlementOption,
    GameplaySnapshotV1,
    LobbyPackageSummary,
)
from engine.contracts.multiplayer_v1.authoring import (
    FinalJudgmentSettlementDefinition,
    MultiplayerStageDefinition,
    NoSettlementDefinition,
)
from engine.contracts.multiplayer_v1.commands import (
    AdvanceStageCommand,
    ConfirmDiscussionCloseCommand,
    ConfirmReadCommand,
    ConfirmSharedChoiceCommand,
    HintConfirmCommand,
    HintRequestCommand,
    MultiplayerCommand,
    RevokeDiscussionCloseCommand,
    RoomResyncCommand,
    SendDiscussionMessageCommand,
    SubmitSettlementCommand,
)
from engine.contracts.multiplayer_v1.reviews import CompletedReviewV1
from engine.contracts.multiplayer_v1.snapshots import build_participant_snapshot
from engine.contracts.multiplayer_v1.state import GameStateV2, HintRuntimeState
from engine.contracts.multiplayer_v1.vocabulary import RoomStatus, SettlementEffect, StagePhase
from engine.core.multiplayer_review import (
    CompletedReviewProjectionError,
    project_completed_review,
)
from engine.core.multiplayer_state_machine import (
    InvalidStageTransitionError,
    complete_final_judgment,
    enter_next_stage,
    reduce_stage_command,
)
from engine.core.package_multiplayer import (
    PackageMultiplayerError,
    multiplayer_stage_contract,
    multiplayer_stage_from_package,
    multiplayer_stages_from_package,
)
from engine.core.package_schema import ScriptPackageImport
from engine.repositories.multiplayer_room_models import (
    StoredMultiplayerRoom,
    StoredRoomMember,
)
from engine.services.session_response_mappers import browser_safe_url

_GAMEPLAY_REDUCER_COMMANDS = (
    ConfirmReadCommand
    | ConfirmDiscussionCloseCommand
    | RevokeDiscussionCloseCommand
    | SubmitSettlementCommand
    | ConfirmSharedChoiceCommand
    | HintRequestCommand
    | HintConfirmCommand
)


@dataclass(frozen=True, slots=True)
class GameplayMutation:
    state: GameStateV2
    state_changed: bool
    event_required: bool
    event_type: str
    event_payload: dict[str, object]


def decode_room_game_state(room: StoredMultiplayerRoom) -> GameStateV2:
    """Strictly restore canonical state and require relational/state agreement."""

    if room.status not in ("active", "completed") or room.state_schema_version != 2:
        raise conflict("ROOM_STATE_INVALID", "多人房间状态无法用于游戏")
    try:
        state = GameStateV2.model_validate_json(
            json.dumps(room.state, ensure_ascii=False, allow_nan=False)
        )
    except (ValidationError, TypeError, ValueError) as exc:
        raise conflict("ROOM_STATE_INVALID", "多人房间规范状态校验失败") from exc
    if (
        state.session_id != room.id
        or state.room_revision != room.revision
        or state.room.status.value != room.status
    ):
        raise conflict("ROOM_STATE_INVALID", "多人房间关系状态与规范状态不一致")
    return state


def apply_gameplay_command(
    *,
    room: StoredMultiplayerRoom,
    member: StoredRoomMember,
    command: MultiplayerCommand,
    package: ScriptPackageImport,
) -> GameplayMutation:
    """Apply one authenticated gameplay command without assigning its revision."""

    if room.status != "active":
        raise conflict("ROOM_NOT_ACTIVE", "房间不再处于游戏中")
    state = decode_room_game_state(room)
    member_id = str(member.id)
    try:
        definition = multiplayer_stage_contract(package, state.stage.stage_id)
        if isinstance(command, SendDiscussionMessageCommand):
            _validate_discussion_message(state, member_id, command)
            player = state.players[member_id]
            if player.character_id is None:
                raise InvalidStageTransitionError("discussion actor has no character")
            return GameplayMutation(
                state=state,
                state_changed=False,
                event_required=True,
                event_type="discussion.message",
                event_payload={
                    "message_id": str(command.payload.message_id),
                    "stage_id": state.stage.stage_id,
                    "member_id": member_id,
                    "character_id": player.character_id,
                    "text": command.payload.text,
                },
            )
        if isinstance(command, AdvanceStageCommand):
            if command.payload.stage_id != state.stage.stage_id:
                raise InvalidStageTransitionError(
                    "command stage_id does not match the current stage"
                )
            next_definition = _next_stage_definition(package, state.stage.stage_id)
            next_state = enter_next_stage(
                state,
                current_definition=definition,
                next_definition=next_definition,
            )
        elif isinstance(command, _GAMEPLAY_REDUCER_COMMANDS):
            next_state = reduce_stage_command(
                state,
                command,
                actor_member_id=member_id,
                definition=definition,
            )
            if (
                isinstance(definition.settlement, FinalJudgmentSettlementDefinition)
                and next_state.stage.phase is StagePhase.REVEAL
            ):
                next_state = complete_final_judgment(
                    next_state,
                    definition=definition,
                    ending_ids=(ending.id for ending in package.endings),
                )
        elif isinstance(command, RoomResyncCommand):
            return GameplayMutation(
                state=state,
                state_changed=False,
                event_required=False,
                event_type="gameplay.resynced",
                event_payload={},
            )
        else:
            raise unprocessable_entity(
                "COMMAND_NOT_AVAILABLE",
                "该命令不属于当前多人游戏能力",
            )
    except InvalidStageTransitionError as exc:
        raise unprocessable_entity(
            "PHASE_MISMATCH",
            "命令与当前阶段状态不匹配，请刷新游戏快照",
        ) from exc
    except PackageMultiplayerError as exc:
        raise conflict("ROOM_PACKAGE_INVALID", "房间固定剧本包的阶段定义无效") from exc

    state_changed = next_state != state
    return GameplayMutation(
        state=next_state,
        state_changed=state_changed,
        event_required=state_changed,
        event_type="gameplay.command_succeeded",
        event_payload={
            "command_type": command.type,
            "stage_id": state.stage.stage_id,
            "actor_member_id": member_id,
        },
    )


def project_gameplay_snapshot(
    *,
    room: StoredMultiplayerRoom,
    member: StoredRoomMember,
    members: Sequence[StoredRoomMember] = (),
    presence_now: datetime | None = None,
    package: ScriptPackageImport,
    event_rows: Sequence[Mapping[str, object]],
) -> GameplaySnapshotV1:
    """Build the playable whitelist projection for one authenticated participant."""

    state = decode_room_game_state(room)
    member_id = str(member.id)
    participant = build_participant_snapshot(
        state,
        member_id=member_id,
        event_head_sequence=room.event_head_sequence,
    )
    try:
        stage_record = multiplayer_stage_from_package(package, participant.stage.stage_id)
        definition = multiplayer_stage_contract(package, participant.stage.stage_id)
        ordered_stages = multiplayer_stages_from_package(package)
        hints = _project_hints(definition, participant.stage.hints)
        settlement = _project_settlement(state, definition, member_id)
    except PackageMultiplayerError as exc:
        raise conflict("ROOM_PACKAGE_INVALID", "房间固定剧本包的阶段定义无效") from exc

    current_index = next(
        (
            index
            for index, candidate in enumerate(ordered_stages)
            if candidate.id == participant.stage.stage_id
        ),
        -1,
    )
    if current_index < 0:
        raise conflict("ROOM_PACKAGE_INVALID", "固定剧本包缺少当前多人阶段")

    chapters_by_id = {chapter.id: chapter for chapter in package.chapters}
    character_id = participant.private_state.character_id
    if character_id is None:
        raise conflict("ROOM_STATE_INVALID", "游戏成员缺少锁定角色")
    try:
        expected_chapter_ids = tuple(
            multiplayer_stage_contract(package, stage.id).chapters[character_id]
            for stage in ordered_stages[: current_index + 1]
        )
    except (KeyError, PackageMultiplayerError) as exc:
        raise conflict("ROOM_PACKAGE_INVALID", "固定剧本包的角色章节顺序无效") from exc
    if participant.private_state.unlocked_chapter_ids != expected_chapter_ids:
        raise conflict("ROOM_STATE_INVALID", "游戏成员已解锁章节与当前阶段不一致")

    chapters: list[GameplayChapter] = []
    for chapter_id in participant.private_state.unlocked_chapter_ids:
        chapter = chapters_by_id.get(chapter_id)
        if chapter is None or chapter.character_id != participant.private_state.character_id:
            raise conflict("ROOM_PACKAGE_INVALID", "房间固定剧本包的私有章节无效")
        chapters.append(
            GameplayChapter(
                id=chapter.id,
                title=chapter.title,
                content=chapter.content,
            )
        )

    characters = {character.id: character for character in package.characters}
    member_presence = {str(item.id): item for item in members}
    freshness_cutoff = presence_now - timedelta(seconds=15) if presence_now is not None else None
    players: list[GameplayPlayer] = []
    for player in participant.players.values():
        if player.character_id is None:
            raise conflict("ROOM_STATE_INVALID", "游戏成员缺少锁定角色")
        character = characters.get(player.character_id)
        if character is None:
            raise conflict("ROOM_PACKAGE_INVALID", "房间固定剧本包缺少锁定角色")
        presence = member_presence.get(player.member_id)
        has_pose = (
            presence is not None
            and presence.scene_x is not None
            and presence.scene_y is not None
            and presence.scene_facing is not None
        )
        online = bool(
            has_pose
            and freshness_cutoff is not None
            and presence is not None
            and presence.scene_updated_at is not None
            and presence.scene_updated_at >= freshness_cutoff
        )
        players.append(
            GameplayPlayer(
                member_id=player.member_id,
                character_id=player.character_id,
                character_name=character.name,
                scene_x=presence.scene_x if online and presence is not None else None,
                scene_y=presence.scene_y if online and presence is not None else None,
                scene_facing=(presence.scene_facing if online and presence is not None else None),
                scene_moving=(
                    bool(presence.scene_moving) if online and presence is not None else False
                ),
                scene_online=online,
            )
        )

    can_advance = (
        participant.room.status is RoomStatus.ACTIVE
        and participant.stage.phase is StagePhase.REVEAL
        and definition.settlement.default_effect is SettlementEffect.RECORD_AND_CONTINUE
        and 0 <= current_index < len(ordered_stages) - 1
    )
    return GameplaySnapshotV1(
        session_id=participant.session_id,
        status=cast(Literal["active", "completed"], participant.room.status.value),
        revision=participant.revision,
        event_head_sequence=participant.event_head_sequence,
        package=LobbyPackageSummary(
            script_id=package.package.id,
            title=package.package.title,
            version=package.package.version,
        ),
        self_member_id=participant.member_id,
        stage_id=participant.stage.stage_id,
        stage_name=stage_record.name,
        phase=participant.stage.phase.value,
        suggested_discussion_minutes=definition.discussion.suggested_minutes,
        players=tuple(players),
        read_member_ids=participant.stage.read_member_ids,
        discussion_close_member_ids=participant.stage.discussion_close_member_ids,
        chapters=tuple(chapters),
        public_materials=_project_materials(
            package,
            definition,
            participant.stage.revealed_material_ids,
        ),
        discussion_messages=_discussion_messages(event_rows, state),
        settlement=settlement,
        hints=hints,
        can_advance=can_advance,
        ending_id=state.ending_id,
    )


def project_multiplayer_review(
    *,
    room: StoredMultiplayerRoom,
    member: StoredRoomMember,
    package: ScriptPackageImport,
) -> CompletedReviewV1:
    """Return completed-only review content from the immutable room package."""

    state = decode_room_game_state(room)
    if room.status != "completed":
        raise conflict("REVIEW_NOT_AVAILABLE", "多人游戏完成后才能查看复盘")
    try:
        definition = multiplayer_stage_contract(package, state.stage.stage_id)
        return project_completed_review(
            state=state,
            member_id=str(member.id),
            package=package,
            final_definition=definition,
        )
    except (PackageMultiplayerError, CompletedReviewProjectionError) as exc:
        raise conflict("ROOM_REVIEW_INVALID", "多人房间复盘内容校验失败") from exc


def _validate_discussion_message(
    state: GameStateV2,
    member_id: str,
    command: SendDiscussionMessageCommand,
) -> None:
    if state.room.status is not RoomStatus.ACTIVE:
        raise InvalidStageTransitionError("discussion requires an active room")
    if member_id not in state.room.required_member_ids:
        raise InvalidStageTransitionError("discussion actor must belong to room")
    if command.payload.stage_id != state.stage.stage_id:
        raise InvalidStageTransitionError("discussion stage_id mismatch")
    if state.stage.phase is not StagePhase.DISCUSS:
        raise InvalidStageTransitionError("messages are allowed only during discussion")


def _next_stage_definition(
    package: ScriptPackageImport,
    current_stage_id: str,
):
    stages = multiplayer_stages_from_package(package)
    for index, stage in enumerate(stages):
        if stage.id != current_stage_id:
            continue
        if index + 1 >= len(stages):
            raise InvalidStageTransitionError("the current stage has no next stage")
        return multiplayer_stage_contract(package, stages[index + 1].id)
    raise PackageMultiplayerError(f"stage.{current_stage_id}")


def _project_hints(
    definition: MultiplayerStageDefinition,
    runtime_hints: tuple[HintRuntimeState, ...],
) -> tuple[GameplayHint, ...]:
    if len(definition.hints) != len(runtime_hints):
        raise conflict("ROOM_STATE_INVALID", "阶段提示状态与固定剧本包不一致")
    projected: list[GameplayHint] = []
    for authored, runtime in zip(definition.hints, runtime_hints, strict=True):
        if authored.id != runtime.hint_id:
            raise conflict("ROOM_STATE_INVALID", "阶段提示状态与固定剧本包不一致")
        projected.append(
            GameplayHint(
                id=authored.id,
                revealed_levels=authored.levels[: runtime.revealed_level],
                pending_level=runtime.pending_level,
                confirming_member_ids=runtime.confirming_member_ids,
            )
        )
    return tuple(projected)


def _project_settlement(
    state: GameStateV2,
    definition: MultiplayerStageDefinition,
    member_id: str,
) -> GameplaySettlement | None:
    authored = definition.settlement
    runtime = state.stage.settlement
    if isinstance(authored, NoSettlementDefinition):
        if runtime is not None:
            raise conflict("ROOM_STATE_INVALID", "阶段结算状态与固定剧本包不一致")
        return None
    if runtime is None or runtime.settlement_id != authored.settlement_id:
        raise conflict("ROOM_STATE_INVALID", "阶段结算状态与固定剧本包不一致")
    if state.stage.phase not in (StagePhase.SETTLE, StagePhase.REVEAL):
        return None
    submission = state.private_by_member[member_id].settlement_submission
    own_option_id = (
        submission.option_id
        if submission is not None and submission.settlement_id == runtime.settlement_id
        else None
    )
    return GameplaySettlement(
        settlement_id=runtime.settlement_id,
        mode=cast(
            Literal["secret_vote", "shared_choice", "final_judgment"],
            runtime.mode.value,
        ),
        question=authored.question,
        options=tuple(
            GameplaySettlementOption(id=option.id, text=option.text) for option in authored.options
        ),
        submitted_member_ids=runtime.submitted_member_ids,
        own_option_id=own_option_id,
        shared_option_id=runtime.shared_option_id,
        outcome_id=runtime.outcome_id,
        revealed=runtime.revealed,
        reveal=authored.reveal.value,
        revealed_ballots=tuple(
            GameplayRevealedBallot(
                member_id=ballot.member_id,
                option_id=ballot.option_id,
            )
            for ballot in runtime.revealed_ballots
        ),
        revealed_option_counts=tuple(
            GameplayRevealedOptionCount(
                option_id=item.option_id,
                count=item.count,
            )
            for item in runtime.revealed_option_counts
        ),
    )


def _project_materials(
    package: ScriptPackageImport,
    definition: MultiplayerStageDefinition,
    revealed_ids: tuple[str, ...],
) -> tuple[GameplayMaterial, ...]:
    authored_ids = tuple(material.id for material in definition.public_materials)
    if any(material_id not in authored_ids for material_id in revealed_ids):
        raise conflict("ROOM_STATE_INVALID", "当前阶段包含未声明的已揭晓公共素材")
    expected_ids = tuple(material_id for material_id in authored_ids if material_id in revealed_ids)
    if revealed_ids != expected_ids:
        raise conflict("ROOM_STATE_INVALID", "当前阶段公共素材顺序无效")
    clues = {clue.id: clue for clue in package.clues}
    evidences = {evidence.id: evidence for evidence in package.evidences}
    media = {asset.id: asset for asset in package.media_assets}
    projected: list[GameplayMaterial] = []
    for material_id in revealed_ids:
        if material_id in clues:
            clue = clues[material_id]
            projected.append(
                GameplayMaterial(
                    id=clue.id,
                    kind="clue",
                    title=clue.name,
                    text=clue.description,
                    url=browser_safe_url(clue.image_url),
                )
            )
        elif material_id in evidences:
            evidence = evidences[material_id]
            projected.append(
                GameplayMaterial(
                    id=evidence.id,
                    kind="evidence",
                    title=evidence.name,
                    text=evidence.description_surface,
                    url=browser_safe_url(evidence.image_url),
                )
            )
        elif material_id in media:
            asset = media[material_id]
            resolution = asset.metadata.get("resolution")
            suffix = f"（{resolution}）" if isinstance(resolution, str) else ""
            projected.append(
                GameplayMaterial(
                    id=asset.id,
                    kind="media",
                    title=asset.id,
                    text=f"已公开{asset.type}素材{suffix}",
                    media_type=asset.type,
                    url=browser_safe_url(asset.file_url),
                )
            )
        else:
            raise conflict("ROOM_PACKAGE_INVALID", "固定剧本包缺少已揭晓公共素材")
    return tuple(projected)


def _discussion_messages(
    event_rows: Sequence[Mapping[str, object]],
    state: GameStateV2,
) -> tuple[GameplayDiscussionMessage, ...]:
    messages: list[GameplayDiscussionMessage] = []
    for row in event_rows:
        if row.get("event_type") != "discussion.message":
            continue
        payload = row.get("payload")
        if not isinstance(payload, Mapping):
            raise conflict("ROOM_EVENT_INVALID", "公共讨论事件格式无效")
        raw = cast(Mapping[object, object], payload)
        try:
            sequence = _event_sequence(row)
            message_id = UUID(_event_text(raw, "message_id"))
            message = GameplayDiscussionMessage(
                sequence=sequence,
                message_id=message_id,
                stage_id=_event_text(raw, "stage_id"),
                member_id=_event_text(raw, "member_id"),
                character_id=_event_text(raw, "character_id"),
                text=_event_text(raw, "text"),
            )
        except (KeyError, TypeError, ValueError, ValidationError) as exc:
            raise conflict("ROOM_EVENT_INVALID", "公共讨论事件格式无效") from exc
        player = state.players.get(message.member_id)
        if player is None or player.character_id != message.character_id:
            raise conflict("ROOM_EVENT_INVALID", "公共讨论事件成员身份无效")
        messages.append(message)
    return tuple(messages)


def _event_sequence(row: Mapping[str, object]) -> int:
    value = row.get("sequence")
    if type(value) is not int or value < 1:
        raise ValueError("invalid event sequence")
    return value


def _event_text(payload: Mapping[object, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str):
        raise TypeError(f"invalid event field: {key}")
    return value
