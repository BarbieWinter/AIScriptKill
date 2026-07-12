"""定义角色及其索引的严格 YAML 模型。"""

from pydantic import Field

from engine.core.package_yaml_base import PackageYamlModel, YamlMapping


class CharacterPersonality(PackageYamlModel):
    """描述 NPC 定义使用的稳定性格特征。"""

    summary: str = Field(description="characters/<character-id>.yml personality.summary")
    traits: list[str] = Field(
        default_factory=list,
        description="characters/<character-id>.yml personality.traits",
    )
    speaking_style: str | None = Field(
        default=None,
        description="characters/<character-id>.yml personality.speaking_style",
    )
    emotional_triggers: list[YamlMapping] = Field(
        default_factory=list,
        description="characters/<character-id>.yml personality.emotional_triggers",
    )


class CharacterKnowledgeEntry(PackageYamlModel):
    """描述角色在特定阶段可知的一项事实。"""

    knows: list[str] = Field(
        default_factory=list,
        description="Knowledge statements available during the stage.",
    )
    doesnt_know: list[str] = Field(
        default_factory=list,
        description="Knowledge statements explicitly unavailable during the stage.",
    )


class CharacterEvidenceReaction(PackageYamlModel):
    """描述角色对一件证物的反应。"""

    evidence_id: str = Field(
        description="characters/<character-id>.yml evidence_reactions[].evidence_id",
    )
    stage_visible: str | None = Field(
        default=None,
        description="characters/<character-id>.yml evidence_reactions[].stage_visible",
    )
    condition: YamlMapping | None = Field(
        default=None,
        description="Optional condition controlling whether this reaction is available.",
    )
    text: str | None = Field(
        default=None,
        description="Legacy reaction text retained for imported packages.",
    )
    reaction_text: str | None = Field(
        default=None,
        description="Documented character response to the evidence.",
    )
    emotional_change: YamlMapping = Field(
        default_factory=dict,
        description="Documented emotion deltas caused by this evidence.",
    )
    state_change: YamlMapping = Field(
        default_factory=dict,
        description="Documented character state deltas caused by this evidence.",
    )
    dialogue_unlock: str | None = Field(
        default=None,
        description="Dialogue branch unlocked by this evidence.",
    )


class CharacterDefinition(PackageYamlModel):
    """定义一个可玩角色或非玩家剧本角色。"""

    id: str = Field(description="characters/<character-id>.yml id")
    name: str = Field(description="characters/<character-id>.yml name")
    portrait: str | None = Field(default=None, description="characters/<character-id>.yml portrait")
    identity: YamlMapping = Field(
        default_factory=dict,
        description="Public and private identity statements for the character.",
    )
    attributes: YamlMapping = Field(
        default_factory=dict,
        description="Documented demographic and role attributes.",
    )
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
    dialogue_strategy: YamlMapping = Field(
        default_factory=dict,
        description="Documented topics, lies, and breakdown conditions.",
    )


class CharacterIndexItem(PackageYamlModel):
    """标识权威索引声明的一个角色。"""

    id: str = Field(description="characters/_index.yml characters[].id")
    name: str | None = Field(default=None, description="characters/_index.yml characters[].name")
    portrait: str | None = Field(
        default=None,
        description="characters/_index.yml characters[].portrait",
    )
    playable: bool = Field(default=True, description="characters/_index.yml characters[].playable")
    is_dm_alter_ego: bool = Field(
        default=False,
        description="characters/_index.yml characters[].is_dm_alter_ego",
    )
    order: int = Field(default=0, description="characters/_index.yml characters[].order")


class CharacterIndex(PackageYamlModel):
    """列出剧本包中必须存在的全部角色文件。"""

    characters: list[CharacterIndexItem] = Field(
        description="characters/_index.yml characters",
    )
    npc_rules: YamlMapping = Field(
        default_factory=dict,
        description="characters/_index.yml npc_rules",
    )
