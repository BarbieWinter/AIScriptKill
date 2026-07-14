from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Literal, cast
from uuid import UUID

from sqlalchemy import case, func, insert, literal, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from engine.api.schemas import CreateSessionRequest, FinalSubmissionRequest
from engine.api.schemas.common import JsonValue
from engine.core.game_state import EvidencePresentation
from engine.db.tables import (
    chat_messages,
    final_submissions,
    game_sessions,
    reviews,
    session_checkpoints,
    session_discoveries,
)
from engine.repositories.session_models import (
    ContentProgress,
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
    for chapter_id in state.unlocked_character_chapters:
        await upsert_discovery(
            db,
            session.id,
            DiscoveryDraft(entity_type="character_chapter", entity_id=chapter_id),
        )
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
    current_result = await db.execute(
        select(game_sessions.c.state).where(game_sessions.c.id == session_id).with_for_update()
    )
    current_raw = current_result.scalar_one_or_none()
    current_state = SessionRuntimeState.model_validate(current_raw or {})
    restored_state = _merge_monotonic_progress(checkpoint.state, current_state)
    stmt = (
        update(game_sessions)
        .where(game_sessions.c.id == session_id)
        .values(state=restored_state.model_dump(mode="json"), updated_at=func.now())
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
    next_state = _merge_state_patch(session.state, effect.state_patch)
    for message in effect.chat_messages:
        message_values = {
            "session_id": session.id,
            "role": message.role,
            "character_id": message.character_id,
            "text": message.text,
            "emotion": message.emotion,
            "metadata": dict[str, JsonValue](),
            "engine_message_id": message.message_id,
        }
        if message.message_id is None:
            await db.execute(insert(chat_messages).values(**message_values))
        else:
            await db.execute(
                pg_insert(chat_messages)
                .values(**message_values)
                .on_conflict_do_nothing(
                    index_elements=(
                        chat_messages.c.session_id,
                        chat_messages.c.engine_message_id,
                    ),
                )
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


async def project_runtime_action(
    db: AsyncSession,
    session: StoredSession,
    state: SessionRuntimeState,
    effect: SessionActionEffect,
) -> StoredSession:
    """将已提交图结果的有限投影和关系表差量幂等写入。"""

    for message in effect.chat_messages:
        message_values = {
            "session_id": session.id,
            "role": message.role,
            "character_id": message.character_id,
            "text": message.text,
            "emotion": message.emotion,
            "metadata": dict[str, JsonValue](),
            "engine_message_id": message.message_id,
        }
        if message.message_id is None:
            await db.execute(insert(chat_messages).values(**message_values))
        else:
            await db.execute(
                pg_insert(chat_messages)
                .values(**message_values)
                .on_conflict_do_nothing(
                    index_elements=(
                        chat_messages.c.session_id,
                        chat_messages.c.engine_message_id,
                    ),
                )
            )
    for discovery in effect.discoveries:
        await upsert_discovery(db, session.id, discovery)
    result = await db.execute(
        update(game_sessions)
        .where(game_sessions.c.id == session.id)
        .values(state=state.model_dump(mode="json"), updated_at=func.now())
        .returning(*SESSION_COLUMNS)
    )
    updated = stored_session_from_row(result.mappings().one())
    await db.commit()
    return updated


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
            suspect=payload.option,
            motive=None,
            key_evidences=[],
            deduction=None,
            score=score,
            result=result_payload,
        ),
    )
    detail = result_payload.get("detail", {})
    selected_option = detail.get("selected_option") if isinstance(detail, dict) else None
    correct_option = detail.get("correct_option") if isinstance(detail, dict) else None
    correct = selected_option == correct_option
    truth_summary = (
        "已证实的范围仅限21:13后门半开、门内灯光和不可辨认的影子。"
        "王大达承认后来发现门闩未扣严并重新扣好，但仍不能据此确认开门者、"
        "进出方向、目的或犯罪。"
    )
    await db.execute(
        insert(reviews).values(
            session_id=session.id,
            score=score,
            max_score=100,
            rating="A" if correct else "未通过",
            breakdown=detail,
            truth_summary=truth_summary,
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


async def mark_content_viewed(
    db: AsyncSession,
    session: StoredSession,
    entity_type: str,
    entity_id: str,
    state_field: Literal["viewed_evidences", "read_character_chapters"],
) -> ContentProgress | None:
    current_result = await db.execute(
        select(game_sessions.c.state)
        .where(game_sessions.c.id == session.id)
        .with_for_update()
    )
    current_raw = current_result.scalar_one_or_none()
    if current_raw is None:
        return None
    current_state = SessionRuntimeState.model_validate(current_raw)

    result = await db.execute(
        update(session_discoveries)
        .where(
            session_discoveries.c.session_id == session.id,
            session_discoveries.c.entity_type == entity_type,
            session_discoveries.c.entity_id == entity_id,
        )
        .values(
            status=case(
                (session_discoveries.c.status == "unlocked", "viewed"),
                else_=session_discoveries.c.status,
            ),
        )
        .returning(session_discoveries.c.entity_id, session_discoveries.c.status)
    )
    row = result.mappings().one_or_none()
    if row is None:
        return None

    current_items = getattr(current_state, state_field)
    next_items = _ordered_union(current_items, (entity_id,))
    if next_items != current_items:
        await db.execute(
            update(game_sessions)
            .where(game_sessions.c.id == session.id)
            .values(
                state=current_state.model_copy(
                    update={state_field: next_items},
                ).model_dump(mode="json"),
                updated_at=func.now(),
            ),
        )
    await db.commit()
    return ContentProgress(entity_id=row["entity_id"], status=row["status"])


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
            set_={
                "status": case(
                    (
                        _discovery_status_rank(discovery.status)
                        > _discovery_status_rank(session_discoveries.c.status),
                        discovery.status,
                    ),
                    else_=session_discoveries.c.status,
                )
            },
        )
    )
    await db.execute(stmt)


_MONOTONIC_STATE_FIELDS = (
    "unlocked_clues",
    "discovered_evidences",
    "viewed_evidences",
    "unlocked_character_chapters",
    "read_character_chapters",
    "evidences_shown_to_npcs",
)


def _merge_state_patch(
    state: SessionRuntimeState,
    patch: dict[str, JsonValue],
) -> SessionRuntimeState:
    values = state.model_dump(mode="python")
    values.update(patch)
    for field_name in _MONOTONIC_STATE_FIELDS:
        patch_value = patch.get(field_name)
        if isinstance(patch_value, list):
            current_items = getattr(state, field_name)
            if field_name == "evidences_shown_to_npcs":
                values[field_name] = _ordered_mapping_union(current_items, patch_value)
            else:
                values[field_name] = _ordered_union(
                    current_items,
                    tuple(item for item in patch_value if isinstance(item, str)),
                )
    return SessionRuntimeState.model_validate(values)


def _merge_monotonic_progress(
    restored: SessionRuntimeState,
    current: SessionRuntimeState,
) -> SessionRuntimeState:
    values = restored.model_dump(mode="python")
    for field_name in _MONOTONIC_STATE_FIELDS:
        restored_items = getattr(restored, field_name)
        current_items = getattr(current, field_name)
        if field_name == "evidences_shown_to_npcs":
            values[field_name] = _ordered_mapping_union(restored_items, current_items)
        else:
            values[field_name] = _ordered_union(restored_items, current_items)
    return SessionRuntimeState.model_validate(values)


def _ordered_union(first: list[str], second: tuple[str, ...] | list[str]) -> list[str]:
    merged = list(first)
    for item in second:
        if item not in merged:
            merged.append(item)
    return merged


def _ordered_mapping_union(
    first: list[EvidencePresentation],
    second: Sequence[object],
) -> list[EvidencePresentation]:
    merged = [
        EvidencePresentation(
            evidence_id=item["evidence_id"],
            character_id=item["character_id"],
        )
        for item in first
    ]
    for item in second:
        if not isinstance(item, dict):
            continue
        mapping = cast(dict[object, object], item)
        evidence_id = mapping.get("evidence_id")
        character_id = mapping.get("character_id")
        if not isinstance(evidence_id, str) or not isinstance(character_id, str):
            continue
        normalized = EvidencePresentation(
            evidence_id=evidence_id,
            character_id=character_id,
        )
        if normalized not in merged:
            merged.append(normalized)
    return merged


def _discovery_status_rank(status: str | ColumnElement[str]) -> ColumnElement[int]:
    expression = literal(status) if isinstance(status, str) else status
    return case(
        (expression == "unlocked", 1),
        (expression == "viewed", 2),
        (expression == "deep_viewed", 3),
        (expression == "used_in_final", 4),
        else_=0,
    )
