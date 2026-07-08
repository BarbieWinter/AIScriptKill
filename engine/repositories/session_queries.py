from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncSession

from engine.db.tables import (
    chat_messages,
    reviews,
    script_characters,
    script_clues,
    script_evidences,
    script_stages,
    session_checkpoints,
    session_discoveries,
)
from engine.repositories.session_models import (
    SessionCheckpoint,
    SessionRuntimeState,
    StoredSession,
)
from engine.repositories.session_rows import session_select, stored_session_from_row

# ── 会话读取 ──


async def get_session(db: AsyncSession, session_id: UUID) -> StoredSession | None:
    result = await db.execute(session_select().where(session_id_column() == session_id))
    row = result.mappings().one_or_none()
    if row is None:
        return None
    return stored_session_from_row(row)


async def get_checkpoint(
    db: AsyncSession,
    session_id: UUID,
    checkpoint_id: str,
) -> SessionCheckpoint | None:
    stmt = (
        select(
            session_checkpoints.c.id,
            session_checkpoints.c.thread_ts,
            session_checkpoints.c.state,
        )
        .where(
            and_(
                session_checkpoints.c.session_id == session_id,
                session_checkpoints.c.thread_ts == checkpoint_id,
            ),
        )
        .order_by(session_checkpoints.c.created_at.desc())
        .limit(1)
    )
    result = await db.execute(stmt)
    row = result.mappings().one_or_none()
    if row is None:
        return None
    return SessionCheckpoint(
        id=row["id"],
        thread_ts=row["thread_ts"],
        state=SessionRuntimeState.model_validate(row["state"]),
    )


# ── 会话内列表查询 ──


async def list_chat_messages(db: AsyncSession, session_id: UUID) -> list[RowMapping]:
    result = await db.execute(
        select(
            chat_messages.c.id,
            chat_messages.c.role,
            chat_messages.c.character_id,
            chat_messages.c.text,
            chat_messages.c.created_at,
            chat_messages.c.emotion,
        )
        .where(chat_messages.c.session_id == session_id)
        .order_by(chat_messages.c.created_at),
    )
    return list(result.mappings().all())


async def list_clues(db: AsyncSession, session: StoredSession) -> list[RowMapping]:
    result = await db.execute(
        select(
            script_clues.c.clue_id,
            script_clues.c.name,
            script_clues.c.image_url,
            script_clues.c.description,
            script_clues.c.is_key,
            script_clues.c.importance,
            session_discoveries.c.discovered_at,
            session_discoveries.c.status,
        )
        .join(
            session_discoveries,
            and_(
                session_discoveries.c.entity_id == script_clues.c.clue_id,
                session_discoveries.c.entity_type == "clue",
                session_discoveries.c.session_id == session.id,
            ),
        )
        .where(script_clues.c.script_id == session.script_id)
        .order_by(session_discoveries.c.discovered_at),
    )
    return list(result.mappings().all())


async def list_evidences(db: AsyncSession, session: StoredSession) -> list[RowMapping]:
    result = await db.execute(
        select(
            script_evidences.c.evidence_id,
            script_evidences.c.name,
            script_evidences.c.image_url,
            script_evidences.c.description_surface,
            session_discoveries.c.status,
        )
        .join(
            session_discoveries,
            and_(
                session_discoveries.c.entity_id == script_evidences.c.evidence_id,
                session_discoveries.c.entity_type == "evidence",
                session_discoveries.c.session_id == session.id,
            ),
        )
        .where(script_evidences.c.script_id == session.script_id)
        .order_by(session_discoveries.c.discovered_at),
    )
    return list(result.mappings().all())


async def list_characters(db: AsyncSession, session: StoredSession) -> list[RowMapping]:
    result = await db.execute(
        select(
            script_characters.c.character_id,
            script_characters.c.name,
            script_characters.c.definition,
        )
        .where(script_characters.c.script_id == session.script_id)
        .order_by(script_characters.c.character_id),
    )
    return list(result.mappings().all())


async def list_cards(db: AsyncSession, session: StoredSession) -> list[RowMapping]:
    result = await db.execute(
        select(
            script_evidences.c.evidence_id,
            script_evidences.c.name,
            script_evidences.c.type,
            script_evidences.c.image_url,
            script_evidences.c.description_surface,
        ).where(
            and_(
                script_evidences.c.script_id == session.script_id,
                script_evidences.c.type.in_(("prop", "skill_card")),
            ),
        ),
    )
    return list(result.mappings().all())


# ── 复盘与阶段查询 ──


async def get_review(db: AsyncSession, session_id: UUID) -> RowMapping | None:
    result = await db.execute(
        select(
            reviews.c.score,
            reviews.c.max_score,
            reviews.c.rating,
            reviews.c.breakdown,
            reviews.c.truth_summary,
            reviews.c.created_at,
        )
        .where(reviews.c.session_id == session_id)
        .order_by(reviews.c.created_at.desc())
        .limit(1),
    )
    return result.mappings().one_or_none()


async def stage_name(db: AsyncSession, script_id: str, stage_id: str) -> str | None:
    result = await db.execute(
        select(script_stages.c.name).where(
            and_(
                script_stages.c.script_id == script_id,
                script_stages.c.stage_id == stage_id,
            ),
        ),
    )
    return result.scalar_one_or_none()


def session_id_column():
    from engine.db.tables import game_sessions

    return game_sessions.c.id
