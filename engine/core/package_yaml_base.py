"""定义共享的严格模型行为和条件类型别名。"""

from typing import ClassVar, TypeAlias

from pydantic import BaseModel, ConfigDict, JsonValue

YamlMapping: TypeAlias = dict[str, JsonValue]


class PackageYamlModel(BaseModel):
    """在全部剧本包 YAML 模型中禁止类型强制转换和未知键。"""

    model_config: ClassVar[ConfigDict] = ConfigDict(
        frozen=True,
        extra="forbid",
        strict=True,
    )
