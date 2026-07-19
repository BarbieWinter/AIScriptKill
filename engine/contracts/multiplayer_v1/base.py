"""定义 Multiplayer v1 契约共享的严格模型行为。"""

from typing import Annotated, ClassVar, TypeAlias

from pydantic import AfterValidator, BaseModel, ConfigDict, Field


class ContractModel(BaseModel):
    """禁止类型强制转换、未知字段和构造后的字段赋值。"""

    model_config: ClassVar[ConfigDict] = ConfigDict(
        frozen=True,
        extra="forbid",
        strict=True,
    )


def _reject_duplicate_strings(values: tuple[str, ...]) -> tuple[str, ...]:
    if len(values) != len(set(values)):
        raise ValueError("sequence values must be unique")
    return values


Identifier: TypeAlias = Annotated[str, Field(min_length=1)]
UniqueIdentifierTuple: TypeAlias = Annotated[
    tuple[Identifier, ...],
    AfterValidator(_reject_duplicate_strings),
]
