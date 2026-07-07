from typing import ClassVar, TypeAlias

from pydantic import BaseModel, ConfigDict, Field

from engine.api.schemas.common import ActionType


class PackageYamlModel(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="allow")


class PackageMetadata(PackageYamlModel):
    id: str = Field(description="package.yml metadata.id")
    title: str = Field(description="package.yml metadata.title")
    version: str = Field(default="1.0.0", description="package.yml metadata.version")


class PackageInfo(PackageYamlModel):
    description: str = Field(default="", description="package.yml info.description")
    genre: list[str] = Field(default_factory=list, description="package.yml info.genre")
    difficulty: int = Field(default=3, ge=1, le=5, description="package.yml info.difficulty")
    duration_minutes: int = Field(default=120, description="package.yml info.duration_minutes")
    min_players: int = Field(default=1, ge=1, description="package.yml info.min_players")
    max_players: int = Field(default=1, description="package.yml info.max_players")


class PackageVisual(PackageYamlModel):
    poster: str | None = Field(default=None, description="package.yml visual.poster")


class PackageEngine(PackageYamlModel):
    entry_stage: str = Field(description="package.yml engine.entry_stage")
    default_ending: str | None = Field(
        default=None,
        description="package.yml engine.default_ending",
    )


class PackageManifest(PackageYamlModel):
    metadata: PackageMetadata
    info: PackageInfo = Field(default_factory=PackageInfo)
    visual: PackageVisual = Field(default_factory=PackageVisual)
    engine: PackageEngine


class StageActionDefinition(PackageYamlModel):
    id: ActionType = Field(description="stages/<stage-id>.yml available_actions[].id")
    label: str = Field(default="", description="stages/<stage-id>.yml available_actions[].label")
    description: str = Field(
        default="",
        description="stages/<stage-id>.yml available_actions[].description",
    )


StageAction: TypeAlias = ActionType | StageActionDefinition


class StageDefinition(PackageYamlModel):
    id: str = Field(description="stages/<stage-id>.yml id")
    name: str = Field(description="stages/<stage-id>.yml name")
    sort_order: int = Field(default=0, description="stages/<stage-id>.yml sort_order")
    available_actions: list[StageAction] = Field(
        default_factory=list,
        description="stages/<stage-id>.yml available_actions",
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


class CharacterPersonality(PackageYamlModel):
    summary: str = Field(description="characters/<character-id>.yml personality.summary")


class CharacterKnowledgeEntry(PackageYamlModel):
    knows: list[str] = Field(default_factory=list)
    doesnt_know: list[str] = Field(default_factory=list)


class CharacterEvidenceReaction(PackageYamlModel):
    evidence_id: str = Field(
        description="characters/<character-id>.yml evidence_reactions[].evidence_id",
    )
    stage_visible: str | None = Field(
        default=None,
        description="characters/<character-id>.yml evidence_reactions[].stage_visible",
    )


class CharacterDefinition(PackageYamlModel):
    id: str = Field(description="characters/<character-id>.yml id")
    name: str = Field(description="characters/<character-id>.yml name")
    personality: CharacterPersonality = Field(
        description="characters/<character-id>.yml personality",
    )
    knowledge: dict[str, CharacterKnowledgeEntry] = Field(
        description="characters/<character-id>.yml knowledge",
    )
    is_dm_alter_ego: bool = Field(
        default=False,
        description="characters/<character-id>.yml is_dm_alter_ego",
    )
    evidence_reactions: list[CharacterEvidenceReaction] = Field(
        default_factory=list,
        description="characters/<character-id>.yml evidence_reactions",
    )


class CharacterIndexItem(PackageYamlModel):
    id: str
    name: str | None = None
    playable: bool = True
    is_dm_alter_ego: bool = False
    order: int = 0


class CharacterIndex(PackageYamlModel):
    characters: list[CharacterIndexItem] = Field(default_factory=list)


class ClueDefinition(PackageYamlModel):
    id: str = Field(description="clues/rounds/<round-id>.yml clues[].id")
    name: str = Field(description="clues/rounds/<round-id>.yml clues[].name")
    description: str = Field(description="clues/rounds/<round-id>.yml clues[].description")
    stage_visible: str | None = Field(
        default=None,
        description="clues/rounds/<round-id>.yml clues[].stage_visible",
    )
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
    round_id: str = Field(description="clues/rounds/<round-id>.yml round_id")
    name: str = Field(default="", description="clues/rounds/<round-id>.yml name")
    stage_visible: str = Field(description="clues/rounds/<round-id>.yml stage_visible")
    clues: list[ClueDefinition] = Field(default_factory=list)


class EvidenceVisual(PackageYamlModel):
    image: str | None = None


class EvidenceDescription(PackageYamlModel):
    surface: str
    deep: str | None = None


class EvidenceDiscovery(PackageYamlModel):
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
    character_id: str = Field(
        description="evidences/<evidence-id>.yml npc_reactions[].character_id",
    )
    text: str = Field(default="", description="evidences/<evidence-id>.yml npc_reactions[].text")


class EvidenceDefinition(PackageYamlModel):
    id: str = Field(description="evidences/<evidence-id>.yml id")
    name: str = Field(description="evidences/<evidence-id>.yml name")
    type: str = Field(default="evidence", description="evidences/<evidence-id>.yml type")
    visual: EvidenceVisual = Field(default_factory=EvidenceVisual)
    description: EvidenceDescription
    discovery: EvidenceDiscovery
    npc_reactions: list[EvidenceNpcReaction] = Field(default_factory=list)


class SceneVisual(PackageYamlModel):
    background: str | None = None


class SceneDefinition(PackageYamlModel):
    id: str
    name: str
    visual: SceneVisual = Field(default_factory=SceneVisual)
    available_in_stages: list[str] = Field(default_factory=list)


class MediaAsset(PackageYamlModel):
    id: str
    file: str
    type: str
    duration_sec: float | None = None
    subtitle_file: str | None = None


class MediaFileDefinition(PackageYamlModel):
    audio_assets: list[MediaAsset] = Field(default_factory=list)
    image_assets: list[MediaAsset] = Field(default_factory=list)


class EndingDefinition(PackageYamlModel):
    id: str = Field(description="endings.yml endings[].id")
    name: str = Field(description="endings.yml endings[].name")
    outcome_text: str = Field(default="", description="endings.yml endings[].outcome_text")


class EndingFileDefinition(PackageYamlModel):
    endings: list[EndingDefinition] = Field(default_factory=list)
