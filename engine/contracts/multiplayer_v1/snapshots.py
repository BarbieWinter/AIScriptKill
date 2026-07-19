"""定义只携带当前参与者私有投影的 Multiplayer v1 快照。"""

from typing import Final, Literal, Self
from uuid import UUID

from pydantic import Field, model_validator

from engine.contracts.multiplayer_v1.base import ContractModel, Identifier
from engine.contracts.multiplayer_v1.state import (
    GameStateV2,
    PlayerState,
    PrivatePlayerState,
    RoomState,
    StageRuntimeState,
)

SNAPSHOT_VERSION: Final = 1


class ParticipantSnapshotV1(ContractModel):
    """向一个房间成员公开房间状态和仅属于该成员的私有状态。"""

    snapshot_version: Literal[1]
    session_id: UUID
    member_id: Identifier
    revision: int = Field(ge=0)
    event_head_sequence: int = Field(ge=0)
    room: RoomState
    players: dict[str, PlayerState]
    stage: StageRuntimeState
    private_state: PrivatePlayerState

    @model_validator(mode="after")
    def validate_participant_projection(self) -> Self:
        player = self.players.get(self.member_id)
        if player is None or self.member_id not in self.room.required_member_ids:
            raise ValueError("snapshot member_id must belong to the room")
        if set(self.players) != set(self.room.required_member_ids):
            raise ValueError("snapshot players must equal room.required_member_ids")
        if player.character_id != self.private_state.character_id:
            raise ValueError("private_state character_id must match the participant player")
        return self


def build_participant_snapshot(
    state: GameStateV2,
    *,
    member_id: str,
    event_head_sequence: int,
) -> ParticipantSnapshotV1:
    """从规范状态裁剪单个成员快照，不复制其他成员私有字段。"""

    try:
        private_state = state.private_by_member[member_id]
    except KeyError as exc:
        raise ValueError("snapshot member_id must belong to the room") from exc
    return ParticipantSnapshotV1(
        snapshot_version=SNAPSHOT_VERSION,
        session_id=state.session_id,
        member_id=member_id,
        revision=state.room_revision,
        event_head_sequence=event_head_sequence,
        room=state.room,
        players=state.players,
        stage=state.stage,
        private_state=private_state,
    )
