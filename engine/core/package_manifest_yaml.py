"""定义严格的剧本包清单和校验规则模型。"""

from pydantic import Field

from engine.contracts.multiplayer_v1.authoring import MultiplayerPolicy
from engine.core.package_yaml_base import PackageYamlModel


class PackageMetadata(PackageYamlModel):
    """标识剧本包、版本和创作适配器。"""

    id: str = Field(description="package.yml metadata.id")
    title: str = Field(description="package.yml metadata.title")
    version: str = Field(default="1.0.0", description="package.yml metadata.version")
    author: str | None = Field(default=None, description="package.yml metadata.author")
    adapter: str | None = Field(default=None, description="package.yml metadata.adapter")


class PackageInfo(PackageYamlModel):
    """描述玩家人数、时长、类型和难度元数据。"""

    description: str = Field(default="", description="package.yml info.description")
    genre: list[str] = Field(default_factory=list, description="package.yml info.genre")
    difficulty: int = Field(default=3, ge=1, le=5, description="package.yml info.difficulty")
    duration_minutes: int = Field(default=120, description="package.yml info.duration_minutes")
    min_players: int = Field(default=1, ge=1, description="package.yml info.min_players")
    max_players: int = Field(default=1, ge=1, description="package.yml info.max_players")


class PackageVisual(PackageYamlModel):
    """声明剧本包级视觉标识资源和样式提示。"""

    poster: str | None = Field(default=None, description="package.yml visual.poster")
    logo: str | None = Field(default=None, description="package.yml visual.logo")
    theme_color: str | None = Field(default=None, description="package.yml visual.theme_color")
    font: str | None = Field(default=None, description="package.yml visual.font")


class PackageDmConfig(PackageYamlModel):
    """配置剧本包的确定性 DM 展示默认值。"""

    style: str = Field(default="immersive", description="package.yml dm_config.style")
    voice_actor: str = Field(default="default", description="package.yml dm_config.voice_actor")
    opening_speech: str = Field(default="", description="package.yml dm_config.opening_speech")


class PackageGuardRules(PackageYamlModel):
    """声明剧本包专用的叙事安全约束。"""

    extra_forbidden_topics: list[str] = Field(
        default_factory=list,
        description="package.yml guard_rules.extra_forbidden_topics",
    )
    character_knowledge_strictness: str = Field(
        default="normal",
        description="package.yml guard_rules.character_knowledge_strictness",
    )


class PackageEngine(PackageYamlModel):
    """声明引擎兼容性、入口阶段和默认结局。"""

    min_engine_version: str | None = Field(
        default=None,
        description="package.yml engine.min_engine_version",
    )
    entry_stage: str = Field(description="package.yml engine.entry_stage")
    default_ending: str | None = Field(
        default=None,
        description="package.yml engine.default_ending",
    )


class PackageManifest(PackageYamlModel):
    """建模完整的 package.yml 文档。"""

    metadata: PackageMetadata = Field(description="package.yml metadata")
    info: PackageInfo = Field(default_factory=PackageInfo, description="package.yml info")
    visual: PackageVisual = Field(default_factory=PackageVisual, description="package.yml visual")
    dm_config: PackageDmConfig = Field(
        default_factory=PackageDmConfig,
        description="package.yml dm_config",
    )
    guard_rules: PackageGuardRules = Field(
        default_factory=PackageGuardRules,
        description="package.yml guard_rules",
    )
    multiplayer: MultiplayerPolicy | None = Field(
        default=None,
        description="package.yml multiplayer",
    )
    engine: PackageEngine = Field(description="package.yml engine")
