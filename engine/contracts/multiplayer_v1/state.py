"""定义 Multiplayer v1 的规范状态和独立状态编解码器。"""

from typing import Final, Literal, Self
from uuid import UUID

from pydantic import Field, model_validator

from engine.contracts.multiplayer_v1.base import (
    ContractModel,
    Identifier,
    UniqueIdentifierTuple,
)
from engine.contracts.multiplayer_v1.vocabulary import RoomStatus, SettlementMode, StagePhase

GAME_STATE_SCHEMA_VERSION: Final = 2


class RoomState(ContractModel):
    """保存房间成员集合、生命周期和当前阶段指针。"""

    status: RoomStatus
    required_member_ids: UniqueIdentifierTuple = Field(min_length=1)
    current_stage_id: Identifier


class PlayerState(ContractModel):
    """保存房间公开可见的成员选角和准备状态。"""

    member_id: Identifier
    character_id: Identifier | None = None
    ready: bool = False


class PrivateSettlementSubmission(ContractModel):
    """仅在对应参与者私有状态中保存其结算选择。"""

    settlement_id: Identifier
    option_id: Identifier


class PrivatePlayerState(ContractModel):
    """保存单个参与者可见的角色章节和未揭晓提交。"""

    character_id: Identifier | None = None
    unlocked_chapter_ids: UniqueIdentifierTuple = ()
    settlement_submission: PrivateSettlementSubmission | None = None


class SettlementRuntimeState(ContractModel):
    """保存结算进度，而不把未揭晓的选项放入房间公开状态。"""

    settlement_id: Identifier
    mode: SettlementMode
    required_member_ids: UniqueIdentifierTuple = Field(min_length=1)
    submitted_member_ids: UniqueIdentifierTuple = ()
    outcome_id: Identifier | None = None
    revealed: bool = False

    @model_validator(mode="after")
    def validate_submission_members(self) -> Self:
        if not set(self.submitted_member_ids).issubset(self.required_member_ids):
            raise ValueError("submitted_member_ids must be a subset of required_member_ids")
        return self


class StageRuntimeState(ContractModel):
    """保存当前阶段的阅读、讨论、结算和揭晓进度。"""

    stage_id: Identifier
    phase: StagePhase
    read_member_ids: UniqueIdentifierTuple = ()
    discussion_close_member_ids: UniqueIdentifierTuple = ()
    settlement: SettlementRuntimeState | None = None
    revealed_material_ids: UniqueIdentifierTuple = ()


class GameStateV2(ContractModel):
    """多人状态的规范 V2 结构；仅约束数据，不实现 reducer。"""

    state_schema_version: Literal[2]
    session_id: UUID
    room_revision: int = Field(ge=0)
    room: RoomState
    players: dict[str, PlayerState]
    private_by_member: dict[str, PrivatePlayerState]
    stage: StageRuntimeState

    @model_validator(mode="after")
    def validate_member_projections(self) -> Self:
        required_members = set(self.room.required_member_ids)
        if set(self.players) != required_members:
            raise ValueError("players keys must equal room.required_member_ids")
        if any(key != player.member_id for key, player in self.players.items()):
            raise ValueError("each players key must equal PlayerState.member_id")
        if not set(self.private_by_member).issubset(required_members):
            raise ValueError("private_by_member keys must belong to the room")
        if self.room.current_stage_id != self.stage.stage_id:
            raise ValueError("room.current_stage_id must equal stage.stage_id")

        for member_id, private_state in self.private_by_member.items():
            public_character = self.players[member_id].character_id
            if private_state.character_id != public_character:
                raise ValueError("private character_id must match the public player projection")
        return self

    @model_validator(mode="after")
    def validate_stage_member_sets(self) -> Self:
        required_members = set(self.room.required_member_ids)
        if not set(self.stage.read_member_ids).issubset(required_members):
            raise ValueError("read_member_ids must be a subset of room members")
        if not set(self.stage.discussion_close_member_ids).issubset(required_members):
            raise ValueError("discussion_close_member_ids must be a subset of room members")
        settlement = self.stage.settlement
        if settlement is not None and not set(settlement.required_member_ids).issubset(
            required_members
        ):
            raise ValueError("settlement members must be a subset of room members")
        return self


def encode_game_state_v2(state: GameStateV2) -> bytes:
    """把规范状态编码成稳定 UTF-8 JSON 字节。"""

    return state.model_dump_json().encode("utf-8")


def decode_game_state_v2(payload: bytes | str) -> GameStateV2:
    """从 JSON 边界严格校验并恢复规范状态。"""

    return GameStateV2.model_validate_json(payload)
