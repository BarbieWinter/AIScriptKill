"""定义人物章节 Markdown frontmatter 的严格模型。"""

from typing import Annotated, Literal, TypeAlias

from pydantic import Field

from engine.core.package_yaml_base import PackageYamlModel


class GameStartChapterRelease(PackageYamlModel):
    """声明章节在所属玩家角色的会话开始时自动授权。"""

    type: Literal["game_start"] = Field(description="Game-start release discriminator.")


class RuleChapterRelease(PackageYamlModel):
    """声明章节只能由同 ID 的确定性剧本事件授权。"""

    type: Literal["rule"] = Field(description="Rule release discriminator.")
    rule_id: str = Field(min_length=1, description="Matching unlock event ID.")


CharacterChapterRelease: TypeAlias = Annotated[
    GameStartChapterRelease | RuleChapterRelease,
    Field(discriminator="type"),
]


class CharacterChapterFrontmatter(PackageYamlModel):
    """描述一个角色专属 Markdown 章节的授权元数据。"""

    chapter_id: str = Field(
        min_length=1,
        description="character_scripts/<character-id>/<chapter-id>.md chapter_id",
    )
    character_id: str = Field(
        min_length=1,
        description="character_scripts/<character-id>/<chapter-id>.md character_id",
    )
    order: int = Field(
        ge=0,
        description="Chapter display order within its character.",
    )
    title: str = Field(min_length=1, description="Chapter display title.")
    visibility: Literal["character_only"] = Field(
        description="Character chapters are only visible to their owning player character.",
    )
    release: CharacterChapterRelease = Field(
        description="Deterministic chapter release declaration.",
    )
    stage_min: str | None = Field(
        default=None,
        min_length=1,
        description="Optional earliest game stage associated with this chapter.",
    )
