"""定义场景、证物、事件和结局的严格 YAML 模型。"""

from typing import Literal, TypeAlias

from pydantic import Field

from engine.core.package_yaml_base import PackageYamlModel, YamlMapping

EvidenceType: TypeAlias = Literal["key_evidence", "evidence", "prop", "skill_card"]


class ClueDefinition(PackageYamlModel):
    """定义一条线索及其发现元数据。"""

    id: str = Field(description="clues/rounds/<round-id>.yml clues[].id")
    name: str = Field(description="clues/rounds/<round-id>.yml clues[].name")
    description: str = Field(description="clues/rounds/<round-id>.yml clues[].description")
    stage_visible: str = Field(description="Required stage that first exposes this clue.")
    image: str | None = Field(default=None, description="clues/rounds/<round-id>.yml clues[].image")
    key_clue: bool = Field(
        default=False,
        description="clues/rounds/<round-id>.yml clues[].key_clue",
    )
    importance: int = Field(
        default=1,
        ge=1,
        le=5,
        description="clues/rounds/<round-id>.yml clues[].importance",
    )
    related_scene: str | None = Field(
        default=None,
        description="clues/rounds/<round-id>.yml clues[].related_scene",
    )
    related_characters: list[str] = Field(
        default_factory=list,
        description="clues/rounds/<round-id>.yml clues[].related_characters",
    )


class ClueRoundDefinition(PackageYamlModel):
    """将有序线索编组为可按阶段寻址的轮次。"""

    round_id: str = Field(description="clues/rounds/<round-id>.yml round_id")
    name: str = Field(default="", description="clues/rounds/<round-id>.yml name")
    stage_visible: str = Field(description="clues/rounds/<round-id>.yml stage_visible")
    clues: list[ClueDefinition] = Field(
        min_length=1,
        description="clues/rounds/<round-id>.yml clues",
    )


class EvidenceVisual(PackageYamlModel):
    """描述证物可供查看的视觉资源。"""

    image: str | None = Field(default=None, description="evidences/<id>.yml visual.image")
    thumbnail: str | None = Field(default=None, description="evidences/<id>.yml visual.thumbnail")


class EvidenceDescription(PackageYamlModel):
    """从摘要、详情和隐藏层级描述证物。"""

    surface: str = Field(description="evidences/<id>.yml description.surface")
    deep: str | None = Field(default=None, description="evidences/<id>.yml description.deep")


class EvidenceDiscovery(PackageYamlModel):
    """定义证物如何对玩家开放。"""

    scene_id: str = Field(description="evidences/<evidence-id>.yml discovery.scene_id")
    hotspot_id: str | None = Field(
        default=None,
        description="evidences/<evidence-id>.yml discovery.hotspot_id",
    )
    stage_visible: str | None = Field(
        default=None,
        description="evidences/<evidence-id>.yml discovery.stage_visible",
    )


class EvidenceNpcReaction(PackageYamlModel):
    """定义 NPC 对证物的条件式反应。"""

    character_id: str = Field(
        description="evidences/<evidence-id>.yml npc_reactions[].character_id",
    )
    text: str = Field(default="", description="evidences/<evidence-id>.yml npc_reactions[].text")
    emotional_impact: YamlMapping = Field(
        default_factory=dict,
        description="evidences/<evidence-id>.yml npc_reactions[].emotional_impact",
    )


class EvidenceDefinition(PackageYamlModel):
    """定义一件类型化证物及其玩法行为。"""

    id: str = Field(description="evidences/<evidence-id>.yml id")
    name: str = Field(description="evidences/<evidence-id>.yml name")
    type: EvidenceType = Field(
        default="evidence",
        description="evidences/<evidence-id>.yml type",
    )
    visual: EvidenceVisual = Field(
        default_factory=EvidenceVisual,
        description="evidences/<evidence-id>.yml visual",
    )
    description: EvidenceDescription = Field(description="evidences/<evidence-id>.yml description")
    discovery: EvidenceDiscovery = Field(description="evidences/<evidence-id>.yml discovery")
    interactions: YamlMapping = Field(
        default_factory=dict,
        description="evidences/<evidence-id>.yml interactions",
    )
    npc_reactions: list[EvidenceNpcReaction] = Field(
        default_factory=list,
        description="evidences/<evidence-id>.yml npc_reactions",
    )


class SceneVisual(PackageYamlModel):
    """描述必要背景和可选场景媒体。"""

    background: str | None = Field(default=None, description="scenes/<id>.yml visual.background")
    ambient_color: str | None = Field(
        default=None,
        description="scenes/<id>.yml visual.ambient_color",
    )
    parallax_layers: list[YamlMapping] = Field(
        default_factory=list,
        description="scenes/<id>.yml visual.parallax_layers",
    )


class SceneDefinition(PackageYamlModel):
    """定义可搜索场景及其可用阶段窗口。"""

    id: str = Field(description="scenes/<id>.yml id")
    name: str = Field(description="scenes/<id>.yml name")
    description: str = Field(default="", description="scenes/<id>.yml description")
    visual: SceneVisual = Field(description="scenes/<id>.yml visual")
    available_in_stages: list[str] = Field(description="scenes/<id>.yml available_in_stages")
    hotspots: list[YamlMapping] = Field(
        default_factory=list,
        description="scenes/<id>.yml hotspots",
    )
    ambient: YamlMapping = Field(default_factory=dict, description="scenes/<id>.yml ambient")


class MediaAsset(PackageYamlModel):
    """描述一个归档支持的媒体资源及展示元数据。"""

    id: str = Field(description="media/*.yml asset id")
    file: str = Field(description="media/*.yml asset file")
    type: str = Field(description="media/*.yml asset type")
    duration_sec: float | None = Field(default=None, description="media/*.yml asset duration_sec")
    subtitle_file: str | None = Field(default=None, description="media/*.yml asset subtitle_file")
    loop: bool | None = Field(default=None, description="media/*.yml asset loop")
    default_volume: float | None = Field(
        default=None,
        description="media/*.yml asset default_volume",
    )
    fade_in: float | None = Field(default=None, description="media/*.yml asset fade_in")
    has_subtitle: bool | None = Field(default=None, description="media/*.yml asset has_subtitle")
    skip_allowed: bool | None = Field(default=None, description="media/*.yml asset skip_allowed")
    trigger_on: str | None = Field(default=None, description="media/*.yml asset trigger_on")
    trigger_stage: str | None = Field(default=None, description="media/*.yml asset trigger_stage")
    usage: list[str] = Field(default_factory=list, description="media/*.yml asset usage")
    resolution: str | None = Field(default=None, description="media/*.yml asset resolution")


class MediaFileDefinition(PackageYamlModel):
    """列出剧本包媒体文件声明的全部媒体资源。"""

    audio_assets: list[MediaAsset] = Field(default_factory=list, description="media audio assets")
    image_assets: list[MediaAsset] = Field(default_factory=list, description="media image assets")


class EndingDefinition(PackageYamlModel):
    """定义一个由条件选中的结局及其媒体序列。"""

    id: str = Field(description="endings.yml endings[].id")
    name: str = Field(description="endings.yml endings[].name")
    condition: YamlMapping = Field(description="endings.yml endings[].condition")
    on_trigger: list[YamlMapping] = Field(
        default_factory=list,
        description="endings.yml endings[].on_trigger",
    )
    outcome_text: str = Field(default="", description="endings.yml endings[].outcome_text")
    rating_bonus: YamlMapping = Field(
        default_factory=dict,
        description="endings.yml endings[].rating_bonus",
    )


class EndingFileDefinition(PackageYamlModel):
    """列出剧本包声明的全部结局。"""

    endings: list[EndingDefinition] = Field(default_factory=list, description="endings.yml endings")
