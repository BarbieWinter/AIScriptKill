"""Generate the browser gameplay contract from the real package and reducer."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Mapping, TypedDict, cast
from uuid import UUID

from engine.contracts.multiplayer_v1.commands import COMMAND_ADAPTER, MultiplayerCommand
from engine.contracts.multiplayer_v1.state import (
    GAME_STATE_SCHEMA_VERSION,
    GameStateV2,
    PlayerState,
    PrivatePlayerState,
    RoomState,
)
from engine.contracts.multiplayer_v1.vocabulary import RoomStatus
from engine.core.multiplayer_state_machine import initialize_stage_runtime
from engine.core.package_loader import load_package_directory
from engine.core.package_multiplayer import (
    multiplayer_package_playability,
    multiplayer_stage_contract,
)
from engine.core.package_schema import ScriptPackageImport
from engine.core.runtime_package_snapshot import (
    decode_runtime_package_snapshot,
    encode_runtime_package_snapshot,
)
from engine.repositories.multiplayer_room_models import StoredMultiplayerRoom, StoredRoomMember
from engine.services.multiplayer_gameplay_service import (
    apply_gameplay_command,
    project_gameplay_snapshot,
    project_multiplayer_review,
)

type JsonValue = None | bool | int | float | str | list[JsonValue] | dict[str, JsonValue]


class GameplayMaterialJson(TypedDict):
    id: str


class GameplaySnapshotJson(TypedDict):
    public_materials: list[GameplayMaterialJson]


class MultiplayerGameplayContract(TypedDict):
    fixture_version: int
    session_id: str
    identities: dict[str, str]
    hint_levels: list[str]
    initial_state: str
    states: dict[str, dict[str, GameplaySnapshotJson]]
    transitions: list[dict[str, object]]
    reviews: dict[str, dict[str, object]]


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_ROOT = REPOSITORY_ROOT / "script-packages" / "mp1-two-player"
OUTPUT_PATH = (
    REPOSITORY_ROOT / "apps" / "web" / "e2e" / "fixtures" / "multiplayer-gameplay-contract.json"
)
SESSION_ID = UUID("22222222-2222-4222-8222-222222222222")
IDENTITIES = {
    "host": UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"),
    "guest": UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"),
}
CHARACTERS = {"host": "investigator", "guest": "insider"}
NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _initial_room() -> tuple[
    StoredMultiplayerRoom,
    dict[str, StoredRoomMember],
    ScriptPackageImport,
]:
    package = load_package_directory(PACKAGE_ROOT, publish=True)
    package_snapshot = encode_runtime_package_snapshot(package)
    definition = multiplayer_stage_contract(package, "investigation")
    member_ids = tuple(str(member_id) for member_id in IDENTITIES.values())
    state = GameStateV2(
        state_schema_version=GAME_STATE_SCHEMA_VERSION,
        session_id=SESSION_ID,
        room_revision=5,
        room=RoomState(
            status=RoomStatus.ACTIVE,
            required_member_ids=member_ids,
            current_stage_id=definition.id,
        ),
        players={
            str(IDENTITIES[identity]): PlayerState(
                member_id=str(IDENTITIES[identity]),
                character_id=character_id,
                ready=True,
            )
            for identity, character_id in CHARACTERS.items()
        },
        private_by_member={
            str(IDENTITIES[identity]): PrivatePlayerState(
                character_id=character_id,
                unlocked_chapter_ids=(definition.chapters[character_id],),
            )
            for identity, character_id in CHARACTERS.items()
        },
        stage=initialize_stage_runtime(definition, required_member_ids=member_ids),
    )
    room = StoredMultiplayerRoom(
        id=SESSION_ID,
        script_id=package.package.id,
        status="active",
        revision=5,
        event_head_sequence=5,
        state_schema_version=GAME_STATE_SCHEMA_VERSION,
        state=state.model_dump(mode="json"),
        runtime_package_version=package.package.version,
        runtime_package_snapshot=dict(package_snapshot.payload),
        runtime_package_sha256=package_snapshot.sha256,
        created_at=NOW,
        started_at=NOW,
        closed_at=None,
    )
    members = {
        identity: StoredRoomMember(
            id=member_id,
            session_id=SESSION_ID,
            principal_id=UUID(
                "cccccccc-cccc-4ccc-8ccc-cccccccccccc"
                if identity == "host"
                else "dddddddd-dddd-4ddd-8ddd-dddddddddddd"
            ),
            room_role="host" if identity == "host" else "player",
            ready_at=NOW,
            joined_at=NOW,
        )
        for identity, member_id in IDENTITIES.items()
    }
    frozen_package = decode_runtime_package_snapshot(
        room.runtime_package_snapshot,
        room.runtime_package_sha256,
        expected_package_id=room.script_id,
        expected_package_version=room.runtime_package_version,
    )
    playability = multiplayer_package_playability(frozen_package)
    if not playability.playable:
        raise AssertionError(playability.diagnostics[0].message)
    return room, members, frozen_package


def _command(
    room: StoredMultiplayerRoom,
    command_type: str,
    payload: Mapping[str, object],
    index: int,
) -> MultiplayerCommand:
    return COMMAND_ADAPTER.validate_python(
        {
            "command_id": UUID(f"00000000-0000-4000-8000-{index:012d}"),
            "expected_revision": room.revision,
            "type": command_type,
            "payload": dict(payload),
        }
    )


def build_multiplayer_gameplay_contract() -> MultiplayerGameplayContract:
    room, members, package = _initial_room()
    states: dict[str, dict[str, GameplaySnapshotJson]] = {}
    transitions: list[dict[str, object]] = []
    command_index = 1

    def record_state(
        name: str,
        *,
        projected_room: StoredMultiplayerRoom | None = None,
        event_rows: tuple[Mapping[str, object], ...] = (),
    ) -> None:
        snapshot_room = projected_room or room
        states[name] = {
            identity: cast(
                GameplaySnapshotJson,
                project_gameplay_snapshot(
                    room=snapshot_room,
                    member=member,
                    members=tuple(members.values()),
                    presence_now=NOW,
                    package=package,
                    event_rows=event_rows,
                ).model_dump(mode="json"),
            )
            for identity, member in members.items()
        }

    def apply(
        source_room: StoredMultiplayerRoom,
        source: str,
        target: str,
        identity: str,
        command_type: str,
        payload: Mapping[str, object],
        *,
        event_rows: tuple[Mapping[str, object], ...] = (),
    ) -> StoredMultiplayerRoom:
        nonlocal command_index
        command = _command(source_room, command_type, payload, command_index)
        command_index += 1
        mutation = apply_gameplay_command(
            room=source_room,
            member=members[identity],
            command=command,
            package=package,
        )
        revision = source_room.revision + 1 if mutation.state_changed else source_room.revision
        event_sequence = (
            source_room.event_head_sequence + 1
            if mutation.event_required
            else source_room.event_head_sequence
        )
        state = mutation.state.model_copy(update={"room_revision": revision})
        target_room = replace(
            source_room,
            status=state.room.status.value,
            revision=revision,
            event_head_sequence=event_sequence,
            state=state.model_dump(mode="json"),
            closed_at=NOW if state.room.status is RoomStatus.COMPLETED else None,
        )
        transitions.append(
            {
                "from": source,
                "to": target,
                "identity": identity,
                "type": command_type,
                "payload": payload,
                "revision": revision,
                "event_sequence": event_sequence,
            }
        )
        record_state(target, projected_room=target_room, event_rows=event_rows)
        return target_room

    def run_remainder(
        source_room: StoredMultiplayerRoom,
        source: str,
        *,
        prefix: str = "",
        event_rows: tuple[Mapping[str, object], ...] = (),
    ) -> StoredMultiplayerRoom:
        branch_room = source_room
        for level in range(1, 4):
            pending = f"{prefix}investigation_hint_{level}_pending"
            revealed = f"{prefix}investigation_hint_{level}"
            branch_room = apply(
                branch_room,
                source,
                pending,
                "host",
                "hint.request",
                {"hint_id": "timeline", "level": level},
                event_rows=event_rows,
            )
            branch_room = apply(
                branch_room,
                pending,
                revealed,
                "guest",
                "hint.confirm",
                {"hint_id": "timeline", "level": level},
                event_rows=event_rows,
            )
            source = revealed

        steps: tuple[tuple[str, str, str, Mapping[str, object]], ...] = (
            (
                f"{prefix}investigation_host_closed",
                "host",
                "discussion.confirm_close",
                {"stage_id": "investigation"},
            ),
            (
                f"{prefix}investigation_settle",
                "guest",
                "discussion.confirm_close",
                {"stage_id": "investigation"},
            ),
            (
                f"{prefix}investigation_host_voted",
                "host",
                "settlement.submit",
                {"settlement_id": "investigation-vote", "option_id": "investigator-account"},
            ),
            (
                f"{prefix}investigation_reveal",
                "guest",
                "settlement.submit",
                {"settlement_id": "investigation-vote", "option_id": "insider-account"},
            ),
            (
                f"{prefix}final_read",
                "host",
                "stage.advance",
                {"stage_id": "investigation"},
            ),
            (
                f"{prefix}final_host_read",
                "host",
                "stage.confirm_read",
                {"stage_id": "final-judgment"},
            ),
            (
                f"{prefix}final_discuss",
                "guest",
                "stage.confirm_read",
                {"stage_id": "final-judgment"},
            ),
            (
                f"{prefix}final_host_closed",
                "host",
                "discussion.confirm_close",
                {"stage_id": "final-judgment"},
            ),
            (
                f"{prefix}final_settle",
                "guest",
                "discussion.confirm_close",
                {"stage_id": "final-judgment"},
            ),
            (
                f"{prefix}final_host_confirmed",
                "host",
                "settlement.confirm_shared_choice",
                {"settlement_id": "final-judgment", "option_id": "timeline-conflict"},
            ),
            (
                f"{prefix}completed",
                "guest",
                "settlement.confirm_shared_choice",
                {"settlement_id": "final-judgment", "option_id": "timeline-conflict"},
            ),
        )
        for target, identity, command_type, payload in steps:
            branch_room = apply(
                branch_room,
                source,
                target,
                identity,
                command_type,
                payload,
                event_rows=event_rows,
            )
            source = target
        return branch_room

    record_state("investigation_read")
    room = apply(
        room,
        "investigation_read",
        "investigation_host_read",
        "host",
        "stage.confirm_read",
        {"stage_id": "investigation"},
    )
    room = apply(
        room,
        "investigation_host_read",
        "investigation_discuss",
        "guest",
        "stage.confirm_read",
        {"stage_id": "investigation"},
    )
    discussion_room = room

    message_payload: dict[str, object] = {
        "stage_id": "investigation",
        "message_id": "33333333-3333-4333-8333-333333333333",
        "text": "门锁没有损坏。",
    }
    message_command = _command(
        discussion_room,
        "discussion.send_message",
        message_payload,
        command_index,
    )
    command_index += 1
    message_mutation = apply_gameplay_command(
        room=discussion_room,
        member=members["host"],
        command=message_command,
        package=package,
    )
    if message_mutation.state_changed or not message_mutation.event_required:
        raise AssertionError("discussion message fixture must be event-only")
    message_event_sequence = discussion_room.event_head_sequence + 1
    message_room = replace(discussion_room, event_head_sequence=message_event_sequence)
    message_event_rows: tuple[Mapping[str, object], ...] = (
        {
            "sequence": message_event_sequence,
            "event_type": message_mutation.event_type,
            "payload": message_mutation.event_payload,
        },
    )
    transitions.append(
        {
            "from": "investigation_discuss",
            "to": "investigation_message",
            "identity": "host",
            "type": "discussion.send_message",
            "payload": message_payload,
            "revision": discussion_room.revision,
            "event_sequence": message_event_sequence,
        }
    )
    record_state(
        "investigation_message",
        projected_room=message_room,
        event_rows=message_event_rows,
    )

    room = run_remainder(discussion_room, "investigation_discuss")
    run_remainder(
        message_room,
        "investigation_message",
        prefix="message_",
        event_rows=message_event_rows,
    )

    reviews = {
        identity: project_multiplayer_review(room=room, member=member, package=package).model_dump(
            mode="json"
        )
        for identity, member in members.items()
    }
    first_hint = multiplayer_stage_contract(package, "investigation").hints[0]
    return {
        "fixture_version": 1,
        "session_id": str(SESSION_ID),
        "identities": {identity: str(member_id) for identity, member_id in IDENTITIES.items()},
        "hint_levels": list(first_hint.levels),
        "initial_state": "investigation_read",
        "states": states,
        "transitions": transitions,
        "reviews": reviews,
    }


def _normalize_json_newlines(value: JsonValue) -> JsonValue:
    if isinstance(value, str):
        return value.replace("\r\n", "\n").replace("\r", "\n")
    if isinstance(value, list):
        return [_normalize_json_newlines(item) for item in value]
    if isinstance(value, dict):
        return {key: _normalize_json_newlines(item) for key, item in value.items()}
    return value


def serialized_multiplayer_gameplay_contract() -> str:
    contract = _normalize_json_newlines(cast(JsonValue, build_multiplayer_gameplay_contract()))
    return (
        json.dumps(
            contract,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )


if __name__ == "__main__":
    OUTPUT_PATH.write_text(
        serialized_multiplayer_gameplay_contract(),
        encoding="utf-8",
        newline="\n",
    )
