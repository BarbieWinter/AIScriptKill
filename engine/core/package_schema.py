from dataclasses import dataclass, field
from typing import Literal, TypeAlias

from engine.api.schemas.common import JsonValue
from engine.api.schemas.packages import PackageStatus

# ── JSON 与媒体类型 ──

JsonMapping: TypeAlias = dict[str, JsonValue]
MediaType: TypeAlias = Literal["bgm", "story", "sfx", "voice", "image", "video"]


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
class EndingRecord:
    id: str
    name: str
    condition: JsonMapping
    on_trigger: tuple[JsonMapping, ...]
    metadata: JsonMapping


@dataclass(frozen=True, slots=True)
class PackageAssetRecord:
    path: str
    content: bytes
    content_type: str


@dataclass(frozen=True, slots=True)
class ScriptPackageImport:
    package: PackageRecord
    stages: tuple[StageRecord, ...]
    characters: tuple[CharacterRecord, ...]
    clues: tuple[ClueRecord, ...] = field(default_factory=tuple)
    evidences: tuple[EvidenceRecord, ...] = field(default_factory=tuple)
    scenes: tuple[SceneRecord, ...] = field(default_factory=tuple)
    media_assets: tuple[MediaRecord, ...] = field(default_factory=tuple)
    endings: tuple[EndingRecord, ...] = field(default_factory=tuple)
    stage_index: JsonMapping = field(default_factory=dict)
    dm_guide: JsonMapping = field(default_factory=dict)
    assets: tuple[PackageAssetRecord, ...] = field(default_factory=tuple)
    warnings: tuple[str, ...] = field(default_factory=tuple)
