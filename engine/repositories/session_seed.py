from dataclasses import dataclass
from typing import ClassVar, Final

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from engine.api.schemas import CreateSessionRequest
from engine.api.schemas.common import ActionType
from engine.db.tables import (
    script_character_chapters,
    script_characters,
    script_packages,
    script_stages,
)
from engine.repositories.session_models import SessionRuntimeState

# ── 初始会话种子模型 ──

DEFAULT_ACTIONS: Final[tuple[ActionType, ...]] = (
    "talk_to_npc",
    "examine_scene",
    "open_clue_board",
)


class PackageRuntimeEngine(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="ignore")

    entry_stage: str


class PackageRuntimeConfig(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="ignore")

    engine: PackageRuntimeEngine


class StageRuntimeDefinition(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="ignore")

    available_actions: list[ActionType] = Field(default_factory=list)
    available_characters: list[str] = Field(default_factory=list)
    available_scenes: list[str] = Field(default_factory=list)


@dataclass(frozen=True, slots=True)
class RuntimeStage:
    name: str
    definition: StageRuntimeDefinition


@dataclass(frozen=True, slots=True)
class SessionSeed:
    stage_id: str
    stage_name: str
    available_actions: tuple[ActionType, ...]
    available_characters: tuple[str, ...]
    current_scene: str
    unlocked_character_chapters: tuple[str, ...]


# ── 剧本包入口读取 ──


async def load_session_seed(
    db: AsyncSession,
    payload: CreateSessionRequest,
) -> SessionSeed | None:
    package = await _published_package(db, payload.script_id)
    if package is None:
        return None

    stage = await _entry_stage(db, payload.script_id, package.engine.entry_stage)
    if stage is None:
        return None

    playable_characters = await _playable_characters(db, payload.script_id)
    if payload.preferred_character_id not in playable_characters:
        return None

    unlocked_character_chapters = await _game_start_chapters(
        db,
        payload.script_id,
        payload.preferred_character_id,
    )
    return SessionSeed(
        stage_id=package.engine.entry_stage,
        stage_name=stage.name,
        available_actions=_available_actions(stage.definition),
        available_characters=_available_characters(stage.definition, playable_characters),
        current_scene=_current_scene(stage.definition),
        unlocked_character_chapters=unlocked_character_chapters,
    )


def initial_session_state(
    payload: CreateSessionRequest,
    seed: SessionSeed,
) -> SessionRuntimeState:
    return SessionRuntimeState(
        player_name=payload.player_name,
        current_stage=seed.stage_id,
        stage_name=seed.stage_name,
        available_actions=list(seed.available_actions),
        available_characters=list(seed.available_characters),
        unlocked_character_chapters=list(seed.unlocked_character_chapters),
        current_scene=seed.current_scene,
    )


# ── 结构表查询 ──


async def _published_package(
    db: AsyncSession,
    script_id: str,
) -> PackageRuntimeConfig | None:
    result = await db.execute(
        select(script_packages.c.config).where(
            and_(
                script_packages.c.id == script_id,
                script_packages.c.status == "published",
            ),
        ),
    )
    raw_config = result.scalar_one_or_none()
    if raw_config is None:
        return None
    return PackageRuntimeConfig.model_validate(raw_config)


async def _entry_stage(
    db: AsyncSession,
    script_id: str,
    stage_id: str,
) -> RuntimeStage | None:
    result = await db.execute(
        select(script_stages.c.name, script_stages.c.definition).where(
            and_(
                script_stages.c.script_id == script_id,
                script_stages.c.stage_id == stage_id,
            ),
        ),
    )
    row = result.mappings().one_or_none()
    if row is None:
        return None
    return RuntimeStage(
        name=str(row["name"]),
        definition=StageRuntimeDefinition.model_validate(row["definition"]),
    )


async def _playable_characters(db: AsyncSession, script_id: str) -> tuple[str, ...]:
    result = await db.execute(
        select(script_characters.c.character_id)
        .where(
            and_(
                script_characters.c.script_id == script_id,
                script_characters.c.is_playable.is_(True),
            ),
        )
        .order_by(script_characters.c.sort_order, script_characters.c.character_id),
    )
    return tuple(str(character_id) for character_id in result.scalars().all())


async def _game_start_chapters(
    db: AsyncSession,
    script_id: str,
    character_id: str,
) -> tuple[str, ...]:
    result = await db.execute(
        select(script_character_chapters.c.chapter_id)
        .where(
            and_(
                script_character_chapters.c.script_id == script_id,
                script_character_chapters.c.character_id == character_id,
                script_character_chapters.c.release["type"].astext == "game_start",
            ),
        )
        .order_by(
            script_character_chapters.c.sort_order,
            script_character_chapters.c.chapter_id,
        ),
    )
    return tuple(str(chapter_id) for chapter_id in result.scalars().all())


# ── 运行时字段派生 ──


def _available_actions(definition: StageRuntimeDefinition) -> tuple[ActionType, ...]:
    if len(definition.available_actions) == 0:
        return DEFAULT_ACTIONS
    return tuple(definition.available_actions)


def _available_characters(
    definition: StageRuntimeDefinition,
    playable_characters: tuple[str, ...],
) -> tuple[str, ...]:
    if len(definition.available_characters) == 0:
        return playable_characters
    return tuple(definition.available_characters)


def _current_scene(definition: StageRuntimeDefinition) -> str:
    if len(definition.available_scenes) == 0:
        return "start"
    return definition.available_scenes[0]
