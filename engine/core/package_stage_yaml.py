"""定义幕和可执行阶段的严格 YAML 模型。"""

from typing import Literal, TypeAlias

from pydantic import Field, JsonValue

from engine.api.schemas.common import ActionType
from engine.core.package_yaml_base import PackageYamlModel, YamlMapping


class StageActionDefinition(PackageYamlModel):
    """描述阶段明确开放的一个动作。"""

    id: ActionType = Field(description="stages/<stage-id>.yml available_actions[].id")
    label: str = Field(default="", description="stages/<stage-id>.yml available_actions[].label")
    description: str = Field(
        default="",
        description="stages/<stage-id>.yml available_actions[].description",
    )


StageAction: TypeAlias = ActionType | StageActionDefinition


class StageMediaTrigger(PackageYamlModel):
    """将一个线索发现事件绑定到一个或多个已校验媒体动作。"""

    event: Literal["clue_discovered"] = Field(description="Supported trigger discriminator.")
    clue_id: str = Field(description="Declared clue whose discovery fires the trigger.")
    then: list[YamlMapping] = Field(
        min_length=1,
        description="Ordered event actions executed after the clue is discovered.",
    )


class StageDefinition(PackageYamlModel):
    """定义一个可执行阶段及其跳转契约。"""

    id: str = Field(description="stages/<stage-id>.yml id")
    name: str = Field(description="stages/<stage-id>.yml name")
    sort_order: int = Field(default=0, description="stages/<stage-id>.yml sort_order")
    act_id: str | None = Field(default=None, description="stages/<stage-id>.yml act_id")
    allowed_transitions: list[str] = Field(
        default_factory=list,
        description="Explicit stage targets allowed from this stage.",
    )
    allow_stage_jump: bool = Field(
        default=False,
        description="Whether forward non-adjacent transitions are allowed.",
    )
    allow_stage_regression: bool = Field(
        default=False,
        description="Whether backward transitions are allowed.",
    )
    entry_conditions: list[JsonValue] = Field(
        description="Conditions that must hold before the stage can be entered.",
    )
    exit_conditions: list[JsonValue] = Field(
        description="Conditions that may complete the stage.",
    )
    available_actions: list[StageAction] = Field(
        description="Player actions enabled during this stage.",
    )
    available_scenes: list[str] = Field(
        default_factory=list,
        description="stages/<stage-id>.yml available_scenes",
    )
    available_clue_rounds: list[str] = Field(
        default_factory=list,
        description="stages/<stage-id>.yml available_clue_rounds",
    )
    available_characters: list[str] = Field(
        default_factory=list,
        description="stages/<stage-id>.yml available_characters",
    )
    on_stage_entry: list[JsonValue] = Field(
        default_factory=list,
        description="Events emitted after entering this stage.",
    )
    on_stage_exit: list[JsonValue] = Field(
        default_factory=list,
        description="Events emitted before leaving this stage.",
    )
    on_clue_discovered: list[JsonValue] = Field(
        default_factory=list,
        description="Clue-discovery event rules supported by the core event bus.",
    )
    media_triggers: list[StageMediaTrigger] = Field(
        default_factory=list,
        description="Media event rules for this stage.",
    )
    special_rules: YamlMapping = Field(
        default_factory=dict,
        description="Documented stage-local gameplay options.",
    )
