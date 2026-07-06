from dataclasses import dataclass, field
from typing import ClassVar, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field

from engine.api.schemas.common import JsonScalar, JsonValue
from engine.api.schemas.packages import PackageStatus

# ── JSON 与媒体类型 ──

JsonMapping: TypeAlias = dict[str, JsonValue]
MediaType: TypeAlias = Literal["bgm", "story", "sfx", "voice", "image", "video"]


# ── YAML 边界模型 ──


class PackageYamlModel(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="allow")


class PackageMetadata(PackageYamlModel):
    id: str = Field(description="metadata.id")
    title: str = Field(description="metadata.title")
    version: str = Field(default="1.0.0", description="metadata.version")


class PackageInfo(PackageYamlModel):
    description: str = Field(default="", description="info.description")
    genre: list[str] = Field(default_factory=list, description="info.genre")
    difficulty: int = Field(default=3, ge=1, le=5, description="info.difficulty")
    duration_minutes: int = Field(default=120, description="info.duration_minutes")
    max_players: int = Field(default=1, description="info.max_players")


class PackageVisual(PackageYamlModel):
    poster: str | None = Field(default=None, description="visual.poster")


class PackageEngine(PackageYamlModel):
    entry_stage: str = Field(description="engine.entry_stage")
    default_ending: str | None = Field(default=None, description="engine.default_ending")


class PackageManifest(PackageYamlModel):
    metadata: PackageMetadata
    info: PackageInfo = Field(default_factory=PackageInfo)
    visual: PackageVisual = Field(default_factory=PackageVisual)
    engine: PackageEngine


class StageDefinition(PackageYamlModel):
    id: str
    name: str
    sort_order: int = 0


class CharacterDefinition(PackageYamlModel):
    id: str
    name: str
    is_dm_alter_ego: bool = False


class CharacterIndexItem(PackageYamlModel):
    id: str
    name: str | None = None
    playable: bool = True
    is_dm_alter_ego: bool = False
    order: int = 0


class CharacterIndex(PackageYamlModel):
    characters: list[CharacterIndexItem] = Field(default_factory=list)


class ClueDefinition(PackageYamlModel):
    id: str
    name: str
    description: str
    image: str | None = None
    key_clue: bool = False
    importance: int = Field(default=1, ge=1, le=5)
    related_scene: str | None = None
    related_characters: list[str] = Field(default_factory=list)


class ClueRoundDefinition(PackageYamlModel):
    round_id: str
    name: str = ""
    stage_visible: str = ""
    clues: list[ClueDefinition] = Field(default_factory=list)


class EvidenceVisual(PackageYamlModel):
    image: str | None = None


class EvidenceDescription(PackageYamlModel):
    surface: str
    deep: str | None = None


class EvidenceDefinition(PackageYamlModel):
    id: str
    name: str
    type: str = "evidence"
    visual: EvidenceVisual = Field(default_factory=EvidenceVisual)
    description: EvidenceDescription
    discovery: dict[str, JsonScalar] = Field(default_factory=dict)


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


# ── 入库记录模型 ──


@dataclass(frozen=True, slots=True)
class PackageRecord:
    id: str
    title: str
    version: str
    status: PackageStatus
    config: JsonMapping


@dataclass(frozen=True, slots=True)
class StageRecord:
    id: str
    name: str
    sort_order: int
    definition: JsonMapping


@dataclass(frozen=True, slots=True)
class CharacterRecord:
    id: str
    name: str
    definition: JsonMapping
    is_playable: bool
    is_dm_alter_ego: bool
    sort_order: int


@dataclass(frozen=True, slots=True)
class ClueRecord:
    id: str
    name: str
    round_id: str
    image_url: str | None
    description: str
    is_key: bool
    importance: int
    metadata: JsonMapping


@dataclass(frozen=True, slots=True)
class EvidenceRecord:
    id: str
    name: str
    image_url: str | None
    description_surface: str
    description_deep: str | None
    type: str
    metadata: JsonMapping


@dataclass(frozen=True, slots=True)
class SceneRecord:
    id: str
    name: str
    background_url: str | None
    definition: JsonMapping


@dataclass(frozen=True, slots=True)
class MediaRecord:
    id: str
    type: MediaType
    file_url: str
    subtitle_url: str | None
    duration_sec: float | None
    metadata: JsonMapping


@dataclass(frozen=True, slots=True)
class ScriptPackageImport:
    package: PackageRecord
    stages: tuple[StageRecord, ...]
    characters: tuple[CharacterRecord, ...]
    clues: tuple[ClueRecord, ...] = field(default_factory=tuple)
    evidences: tuple[EvidenceRecord, ...] = field(default_factory=tuple)
    scenes: tuple[SceneRecord, ...] = field(default_factory=tuple)
    media_assets: tuple[MediaRecord, ...] = field(default_factory=tuple)
    warnings: tuple[str, ...] = field(default_factory=tuple)
