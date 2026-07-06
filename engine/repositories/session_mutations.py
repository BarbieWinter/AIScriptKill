from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, insert, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from engine.api.schemas import CreateSessionRequest, FinalSubmissionRequest
from engine.api.schemas.common import JsonValue
from engine.db.tables import (
    chat_messages,
    final_submissions,
    game_sessions,
    reviews,
    session_checkpoints,
    session_discoveries,
)
from engine.repositories.session_models import (
    DiscoveryDraft,
    SessionActionEffect,
    SessionRuntimeState,
    StoredSession,
)
from engine.repositories.session_queries import get_checkpoint
from engine.repositories.session_rows import (
    SESSION_COLUMNS,
    stored_session_from_row,
)
from engine.repositories.session_seed import initial_session_state, load_session_seed

# ── 会话写入 ──


async def create_session(
    db: AsyncSession,
    payload: CreateSessionRequest,
    player_id: UUID | None,
) -> StoredSession | None:
    seed = await load_session_seed(db, payload)
    if seed is None:
        return None

    state = initial_session_state(payload, seed)
    stmt = (
        insert(game_sessions)
        .values(
            script_id=payload.script_id,
            player_id=player_id,
            player_character_id=payload.preferred_character_id,
            state=state.model_dump(mode="json"),
            status="in_progress",
        )
        .returning(*SESSION_COLUMNS)
    )
    result = await db.execute(stmt)
    session = stored_session_from_row(result.mappings().one())
    await create_checkpoint(db, session.id, "initial", session.state, None)
    await db.commit()
    return session


async def restore_checkpoint(
    db: AsyncSession,
    session_id: UUID,
    checkpoint_id: str,
) -> StoredSession | None:
    checkpoint = await get_checkpoint(db, session_id, checkpoint_id)
    if checkpoint is None:
        return None
    stmt = (
        update(game_sessions)
        .where(game_sessions.c.id == session_id)
        .values(state=checkpoint.state.model_dump(mode="json"), updated_at=func.now())
        .returning(*SESSION_COLUMNS)
    )
    result = await db.execute(stmt)
    row = result.mappings().one_or_none()
    await db.commit()
    if row is None:
        return None
    return stored_session_from_row(row)


async def apply_action(
    db: AsyncSession,
    session: StoredSession,
    effect: SessionActionEffect,
) -> StoredSession:
    next_state = session.state.model_copy(update=effect.state_patch)
    for message in effect.chat_messages:
        await db.execute(
            insert(chat_messages).values(
                session_id=session.id,
                role=message.role,
                character_id=message.character_id,
                text=message.text,
                emotion=message.emotion,
                metadata={},
            ),
        )
    for discovery in effect.discoveries:
        await upsert_discovery(db, session.id, discovery)
    stmt = (
        update(game_sessions)
        .where(game_sessions.c.id == session.id)
        .values(state=next_state.model_dump(mode="json"), updated_at=func.now())
        .returning(*SESSION_COLUMNS)
    )
    result = await db.execute(stmt)
    updated_session = stored_session_from_row(result.mappings().one())
    await create_checkpoint(
        db,
        updated_session.id,
        datetime.now(UTC).isoformat(),
        updated_session.state,
        None,
    )
    await db.commit()
    return updated_session


async def save_final_submission(
    db: AsyncSession,
    session: StoredSession,
    payload: FinalSubmissionRequest,
    result_payload: dict[str, JsonValue],
    score: int,
) -> StoredSession:
    await db.execute(
        insert(final_submissions).values(
            session_id=session.id,
            suspect=payload.suspect,
            motive=payload.motive,
            key_evidences=payload.key_evidences,
            deduction=payload.deduction,
            score=score,
            result=result_payload,
        ),
    )
    await db.execute(
        insert(reviews).values(
            session_id=session.id,
            score=score,
            max_score=100,
            rating="A",
            breakdown=result_payload.get("detail", {}),
            truth_summary="真相已提交，复盘内容等待评分服务补全。",
        ),
    )
    next_state = session.state.model_copy(
        update={
            "final_submission": payload.model_dump(mode="json"),
            "ending_id": result_payload.get("ending_id"),
        },
    )
    stmt = (
        update(game_sessions)
        .where(game_sessions.c.id == session.id)
        .values(
            state=next_state.model_dump(mode="json"),
            status="completed",
            updated_at=func.now(),
        )
        .returning(*SESSION_COLUMNS)
    )
    result = await db.execute(stmt)
    row = result.mappings().one()
    await db.commit()
    return stored_session_from_row(row)


# ── 检查点与发现记录写入 ──


async def create_checkpoint(
    db: AsyncSession,
    session_id: UUID,
    thread_ts: str,
    state: SessionRuntimeState,
    parent_ts: str | None,
) -> None:
    await db.execute(
        insert(session_checkpoints).values(
            session_id=session_id,
            thread_ts=thread_ts,
            parent_ts=parent_ts,
            state=state.model_dump(mode="json"),
        ),
    )


async def upsert_discovery(
    db: AsyncSession,
    session_id: UUID,
    discovery: DiscoveryDraft,
) -> None:
    stmt = (
        pg_insert(session_discoveries)
        .values(
            session_id=session_id,
            entity_type=discovery.entity_type,
            entity_id=discovery.entity_id,
            status=discovery.status,
        )
        .on_conflict_do_update(
            index_elements=[
                session_discoveries.c.session_id,
                session_discoveries.c.entity_type,
                session_discoveries.c.entity_id,
            ],
            set_={"status": discovery.status},
        )
    )
    await db.execute(stmt)
