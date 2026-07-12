"""定义剧本包解析产生的规范化不可变记录。"""

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
    """携带剧本包标识和可安全持久化的配置。"""

    id: str
    title: str
    version: str
    status: PackageStatus
    config: JsonMapping


@dataclass(frozen=True, slots=True)
class StageRecord:
    """携带一个权威阶段及其可执行定义。"""

    id: str
    name: str
    sort_order: int
    definition: JsonMapping


@dataclass(frozen=True, slots=True)
class CharacterRecord:
    """携带一个角色及其规范化剧本包定义。"""

    id: str
    name: str
    definition: JsonMapping
    is_playable: bool
    is_dm_alter_ego: bool
    sort_order: int


@dataclass(frozen=True, slots=True)
class ClueRecord:
    """携带从线索轮次文档展开的一条线索。"""

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
    """携带一件类型化证物及其发现元数据。"""

    id: str
    name: str
    image_url: str | None
    description_surface: str
    description_deep: str | None
    type: str
    metadata: JsonMapping


@dataclass(frozen=True, slots=True)
class SceneRecord:
    """携带一个可搜索场景及其规范化定义。"""

    id: str
    name: str
    background_url: str | None
    definition: JsonMapping


@dataclass(frozen=True, slots=True)
class MediaRecord:
    """携带一个已声明媒体资源及展示元数据。"""

    id: str
    type: MediaType
    file_url: str
    subtitle_url: str | None
    duration_sec: float | None
    metadata: JsonMapping


@dataclass(frozen=True, slots=True)
class EndingRecord:
    """携带一个结局条件及其有序触发动作。"""

    id: str
    name: str
    condition: JsonMapping
    on_trigger: tuple[JsonMapping, ...]
    metadata: JsonMapping


@dataclass(frozen=True, slots=True)
class PackageAssetRecord:
    """携带一个私有存储上传前已受限的归档资源。"""

    path: str
    content: bytes
    content_type: str


@dataclass(frozen=True, slots=True)
class ScriptPackageImport:
    """汇总已完整校验且可原子持久化的剧本包。"""

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
