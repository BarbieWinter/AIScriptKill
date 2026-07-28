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


class RevealedBallot(ContractModel):
    """保存结算完成后允许公开的一张实名选票。"""

    member_id: Identifier
    option_id: Identifier


class RevealedOptionCount(ContractModel):
    """保存结算完成后按创作选项顺序公开的一项聚合计数。"""

    option_id: Identifier
    count: int = Field(ge=0)


class SettlementRuntimeState(ContractModel):
    """保存结算进度，而不把未揭晓的秘密选项放入公开状态。"""

    settlement_id: Identifier
    mode: SettlementMode
    required_member_ids: UniqueIdentifierTuple = Field(min_length=1)
    submitted_member_ids: UniqueIdentifierTuple = ()
    shared_option_id: Identifier | None = None
    outcome_id: Identifier | None = None
    revealed: bool = False
    revealed_ballots: tuple[RevealedBallot, ...] = ()
    revealed_option_counts: tuple[RevealedOptionCount, ...] = ()

    @model_validator(mode="after")
    def validate_settlement_progress(self) -> Self:
        required_members = set(self.required_member_ids)
        if not set(self.submitted_member_ids).issubset(required_members):
            raise ValueError("submitted_member_ids must be a subset of required_member_ids")
        expected_submitted = tuple(
            member_id
            for member_id in self.required_member_ids
            if member_id in self.submitted_member_ids
        )
        if self.submitted_member_ids != expected_submitted:
            raise ValueError("submitted_member_ids must use canonical required-member order")

        ballot_member_ids = tuple(ballot.member_id for ballot in self.revealed_ballots)
        if len(ballot_member_ids) != len(set(ballot_member_ids)):
            raise ValueError("revealed ballot member ids must be unique")
        if not set(ballot_member_ids).issubset(required_members):
            raise ValueError("revealed ballot members must belong to the settlement")
        expected_ballot_members = tuple(
            member_id for member_id in self.required_member_ids if member_id in ballot_member_ids
        )
        if ballot_member_ids != expected_ballot_members:
            raise ValueError("revealed_ballots must use canonical required-member order")
        if self.revealed_ballots and ballot_member_ids != self.required_member_ids:
            raise ValueError("revealed_ballots must include all required members")

        count_option_ids = tuple(item.option_id for item in self.revealed_option_counts)
        if len(count_option_ids) != len(set(count_option_ids)):
            raise ValueError("revealed option count ids must be unique")
        if self.revealed_option_counts and sum(
            item.count for item in self.revealed_option_counts
        ) != len(self.submitted_member_ids):
            raise ValueError("revealed option counts must sum to submitted members")

        if self.revealed_ballots and self.revealed_option_counts:
            raise ValueError("revealed ballots and option counts are mutually exclusive")
        if (self.revealed_ballots or self.revealed_option_counts) and not self.revealed:
            raise ValueError("public settlement results require a revealed settlement")
        if self.revealed and self.submitted_member_ids != self.required_member_ids:
            raise ValueError("a revealed settlement requires all required submissions")
        if self.revealed and self.outcome_id is None:
            raise ValueError("a revealed settlement requires outcome_id")
        if not self.revealed and self.outcome_id is not None:
            raise ValueError("an unrevealed settlement cannot expose outcome_id")
        if self.shared_option_id is not None and (
            self.revealed_ballots or self.revealed_option_counts
        ):
            raise ValueError("a shared settlement cannot expose individual results")
        return self


class HintRuntimeState(ContractModel):
    """保存一个三级公共提示的顺序揭晓与全员确认进度。"""

    hint_id: Identifier
    revealed_level: int = Field(default=0, ge=0, le=3)
    pending_level: int | None = Field(default=None, ge=1, le=3)
    confirming_member_ids: UniqueIdentifierTuple = ()

    @model_validator(mode="after")
    def validate_hint_progress(self) -> Self:
        if self.pending_level is None:
            if self.confirming_member_ids:
                raise ValueError("confirming_member_ids require a pending hint level")
        elif self.pending_level != self.revealed_level + 1:
            raise ValueError("pending_level must be the next sequential level")
        return self


class StageRuntimeState(ContractModel):
    """保存当前阶段的阅读、讨论、结算、提示和揭晓进度。"""

    stage_id: Identifier
    phase: StagePhase
    read_member_ids: UniqueIdentifierTuple = ()
    discussion_close_member_ids: UniqueIdentifierTuple = ()
    settlement: SettlementRuntimeState | None = None
    revealed_material_ids: UniqueIdentifierTuple = ()
    hints: tuple[HintRuntimeState, ...] = ()

    @model_validator(mode="after")
    def validate_unique_hint_ids(self) -> Self:
        hint_ids = tuple(hint.hint_id for hint in self.hints)
        if len(hint_ids) != len(set(hint_ids)):
            raise ValueError("stage hint ids must be unique")
        return self


class GameStateV2(ContractModel):
    """多人状态的规范 V2 结构；状态变更由独立纯 reducer 完成。"""

    state_schema_version: Literal[2]
    session_id: UUID
    room_revision: int = Field(ge=0)
    room: RoomState
    players: dict[str, PlayerState]
    private_by_member: dict[str, PrivatePlayerState]
    stage: StageRuntimeState
    prior_revealed_material_ids: UniqueIdentifierTuple = ()
    ending_id: Identifier | None = None

    @model_validator(mode="after")
    def validate_member_projections(self) -> Self:
        required_member_ids = self.room.required_member_ids
        required_members = set(required_member_ids)
        if set(self.players) != required_members:
            raise ValueError("players keys must equal room.required_member_ids")
        if any(key != player.member_id for key, player in self.players.items()):
            raise ValueError("each players key must equal PlayerState.member_id")
        if set(self.private_by_member) != required_members:
            raise ValueError("private_by_member keys must equal room.required_member_ids")
        if self.room.current_stage_id != self.stage.stage_id:
            raise ValueError("room.current_stage_id must equal stage.stage_id")

        for member_id, private_state in self.private_by_member.items():
            public_character = self.players[member_id].character_id
            if private_state.character_id != public_character:
                raise ValueError("private character_id must match the public player projection")

        if self.room.status is RoomStatus.COMPLETED:
            if self.ending_id is None:
                raise ValueError("a completed room requires ending_id")
            settlement = self.stage.settlement
            if (
                self.stage.phase is not StagePhase.REVEAL
                or settlement is None
                or not settlement.revealed
                or settlement.outcome_id is None
            ):
                raise ValueError("a completed room requires a revealed final settlement outcome")
        elif self.ending_id is not None:
            raise ValueError("only a completed room may expose ending_id")
        return self

    @model_validator(mode="after")
    def validate_stage_member_sets(self) -> Self:
        required_member_ids = self.room.required_member_ids
        required_members = set(required_member_ids)
        for field_name, member_ids in (
            ("read_member_ids", self.stage.read_member_ids),
            ("discussion_close_member_ids", self.stage.discussion_close_member_ids),
        ):
            if not set(member_ids).issubset(required_members):
                raise ValueError(f"{field_name} must be a subset of room members")
            expected = tuple(
                member_id for member_id in required_member_ids if member_id in member_ids
            )
            if member_ids != expected:
                raise ValueError(f"{field_name} must use canonical room member order")

        settlement = self.stage.settlement
        if settlement is not None and settlement.required_member_ids != required_member_ids:
            raise ValueError("settlement members must equal room members in canonical order")

        for hint in self.stage.hints:
            if not set(hint.confirming_member_ids).issubset(required_members):
                raise ValueError("hint confirming members must be a subset of room members")
            expected = tuple(
                member_id
                for member_id in required_member_ids
                if member_id in hint.confirming_member_ids
            )
            if hint.confirming_member_ids != expected:
                raise ValueError("hint confirmations must use canonical room member order")
        return self


def encode_game_state_v2(state: GameStateV2) -> bytes:
    """把规范状态编码成稳定 UTF-8 JSON 字节。"""

    return state.model_dump_json().encode("utf-8")


def decode_game_state_v2(payload: bytes | str) -> GameStateV2:
    """从 JSON 边界严格校验并恢复规范状态。"""

    return GameStateV2.model_validate_json(payload)
