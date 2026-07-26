"""定义 Multiplayer v1 的幂等命令和执行结果契约。"""

from typing import Annotated, Final, Literal, Self, TypeAlias
from uuid import UUID

from pydantic import BeforeValidator, Field, TypeAdapter, model_validator

from engine.contracts.multiplayer_v1.base import ContractModel, Identifier
from engine.contracts.multiplayer_v1.errors import CommandError
from engine.contracts.multiplayer_v1.vocabulary import CommandStatus


def _parse_wire_uuid(value: object) -> object:
    """Parse UUID strings at the JSON boundary while retaining strict models."""

    if isinstance(value, str):
        return UUID(value)
    return value


WireUuid: TypeAlias = Annotated[UUID, BeforeValidator(_parse_wire_uuid)]


class _CommandBase(ContractModel):
    """提供全部客户端命令共享的幂等和并发控制字段。"""

    command_id: WireUuid
    expected_revision: int = Field(ge=0)


class AssignCharacterPayload(ContractModel):
    character_id: Identifier


class AssignCharacterCommand(_CommandBase):
    type: Literal["room.assign_character"]
    payload: AssignCharacterPayload


class UnassignCharacterPayload(ContractModel):
    pass


class UnassignCharacterCommand(_CommandBase):
    type: Literal["room.unassign_character"]
    payload: UnassignCharacterPayload


class ReadyPayload(ContractModel):
    ready: bool = True


class ReadyCommand(_CommandBase):
    type: Literal["room.ready"]
    payload: ReadyPayload


class StartRoomPayload(ContractModel):
    pass


class StartRoomCommand(_CommandBase):
    type: Literal["room.start"]
    payload: StartRoomPayload


class EndIncompletePayload(ContractModel):
    reason: str | None = Field(default=None, min_length=1)


class EndIncompleteCommand(_CommandBase):
    type: Literal["room.end_incomplete"]
    payload: EndIncompletePayload


class StageCommandPayload(ContractModel):
    stage_id: Identifier


class ConfirmReadCommand(_CommandBase):
    type: Literal["stage.confirm_read"]
    payload: StageCommandPayload


class AdvanceStageCommand(_CommandBase):
    """Request server-selected progression from an observable reveal phase."""

    type: Literal["stage.advance"]
    payload: StageCommandPayload


class SendDiscussionMessagePayload(StageCommandPayload):
    message_id: WireUuid
    text: str = Field(min_length=1, max_length=4_000)


class SendDiscussionMessageCommand(_CommandBase):
    type: Literal["discussion.send_message"]
    payload: SendDiscussionMessagePayload


class ConfirmDiscussionCloseCommand(_CommandBase):
    type: Literal["discussion.confirm_close"]
    payload: StageCommandPayload


class RevokeDiscussionCloseCommand(_CommandBase):
    type: Literal["discussion.revoke_close"]
    payload: StageCommandPayload


class SubmitSettlementPayload(ContractModel):
    settlement_id: Identifier
    option_id: Identifier


class SubmitSettlementCommand(_CommandBase):
    type: Literal["settlement.submit"]
    payload: SubmitSettlementPayload


class ConfirmSharedChoicePayload(ContractModel):
    settlement_id: Identifier
    option_id: Identifier


class ConfirmSharedChoiceCommand(_CommandBase):
    type: Literal["settlement.confirm_shared_choice"]
    payload: ConfirmSharedChoicePayload


class HintRequestPayload(ContractModel):
    hint_id: Identifier
    level: int = Field(ge=1, le=3)


class HintRequestCommand(_CommandBase):
    type: Literal["hint.request"]
    payload: HintRequestPayload


class HintConfirmPayload(ContractModel):
    hint_id: Identifier
    level: int = Field(ge=1, le=3)


class HintConfirmCommand(_CommandBase):
    type: Literal["hint.confirm"]
    payload: HintConfirmPayload


class RoomResyncPayload(ContractModel):
    last_event_sequence: int | None = Field(default=None, ge=0)


class RoomResyncCommand(_CommandBase):
    """请求参与者安全快照；运行时不得因该命令推进 room revision。"""

    type: Literal["room.resync"]
    payload: RoomResyncPayload


MultiplayerCommand: TypeAlias = Annotated[
    AssignCharacterCommand
    | UnassignCharacterCommand
    | ReadyCommand
    | StartRoomCommand
    | EndIncompleteCommand
    | ConfirmReadCommand
    | AdvanceStageCommand
    | SendDiscussionMessageCommand
    | ConfirmDiscussionCloseCommand
    | RevokeDiscussionCloseCommand
    | SubmitSettlementCommand
    | ConfirmSharedChoiceCommand
    | HintRequestCommand
    | HintConfirmCommand
    | RoomResyncCommand,
    Field(discriminator="type"),
]
COMMAND_ADAPTER: Final[TypeAdapter[MultiplayerCommand]] = TypeAdapter(MultiplayerCommand)


class CommandResultData(ContractModel):
    """列出命令接收后产生的事件，供调用方关联重放。"""

    event_ids: tuple[UUID, ...] = ()


class CommandResultV1(ContractModel):
    """返回命令的确定性结果、当前修订和重放标记。"""

    command_id: UUID
    status: CommandStatus
    revision: int = Field(ge=0)
    event_sequence: int = Field(ge=0)
    result: CommandResultData | None = None
    error: CommandError | None = None
    replayed: bool = False

    @model_validator(mode="after")
    def validate_status_payload(self) -> Self:
        if self.status is CommandStatus.ACCEPTED:
            if self.result is None or self.error is not None:
                raise ValueError("accepted command requires result and forbids error")
        elif self.result is not None or self.error is None:
            raise ValueError("rejected command requires error and forbids result")
        return self
