from uuid import UUID

from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncSession

from engine.api.schemas import CreateSessionRequest, FinalSubmissionRequest
from engine.api.schemas.common import JsonValue
from engine.repositories.session_context import apply_session_context
from engine.repositories.session_models import (
    CharacterChapterAccess,
    ChatMessageDraft,
    ContentProgress,
    DiscoveryDraft,
    SessionActionEffect,
    SessionCheckpoint,
    SessionRuntimeState,
    StoredSession,
)
from engine.repositories.session_mutations import (
    apply_action as persist_action,
)
from engine.repositories.session_mutations import (
    create_checkpoint as persist_checkpoint,
)
from engine.repositories.session_mutations import (
    create_session as persist_session,
)
from engine.repositories.session_mutations import (
    mark_content_viewed as persist_content_viewed,
)
from engine.repositories.session_mutations import (
    project_runtime_action as persist_runtime_action,
)
from engine.repositories.session_mutations import (
    restore_checkpoint as persist_restore,
)
from engine.repositories.session_mutations import (
    save_final_submission as persist_submission,
)
from engine.repositories.session_queries import (
    get_character_chapter as fetch_character_chapter,
)
from engine.repositories.session_queries import (
    get_checkpoint as fetch_checkpoint,
)
from engine.repositories.session_queries import (
    get_review as fetch_review,
)
from engine.repositories.session_queries import (
    get_session as fetch_session,
)
from engine.repositories.session_queries import (
    list_cards as fetch_cards,
)
from engine.repositories.session_queries import (
    list_character_chapters as fetch_character_chapters,
)
from engine.repositories.session_queries import (
    list_characters as fetch_characters,
)
from engine.repositories.session_queries import (
    list_chat_messages as fetch_chat_messages,
)
from engine.repositories.session_queries import (
    list_clues as fetch_clues,
)
from engine.repositories.session_queries import (
    list_evidences as fetch_evidences,
)
from engine.repositories.session_queries import (
    list_read_character_chapters as fetch_read_character_chapters,
)
from engine.repositories.session_queries import (
    stage_name as fetch_stage_name,
)

# ── 会话持久化 Repository 门面 ──


class SessionRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    # 会话生命周期写入
    async def create_session(
        self,
        payload: CreateSessionRequest,
        player_id: UUID | None,
    ) -> StoredSession | None:
        return await persist_session(self._db, payload, player_id)

    async def get_session(self, session_id: UUID) -> StoredSession | None:
        return await fetch_session(self._db, session_id)

    async def restore_checkpoint(
        self,
        session_id: UUID,
        checkpoint_id: str,
    ) -> StoredSession | None:
        return await persist_restore(self._db, session_id, checkpoint_id)

    async def apply_action(
        self,
        session: StoredSession,
        effect: SessionActionEffect,
    ) -> StoredSession:
        return await persist_action(self._db, session, effect)

    async def project_runtime_action(
        self,
        session: StoredSession,
        state: SessionRuntimeState,
        effect: SessionActionEffect,
    ) -> StoredSession:
        return await persist_runtime_action(self._db, session, state, effect)

    # 最终提交与复盘写入
    async def save_final_submission(
        self,
        session: StoredSession,
        payload: FinalSubmissionRequest,
        result_payload: dict[str, JsonValue],
        score: int,
    ) -> StoredSession:
        return await persist_submission(self._db, session, payload, result_payload, score)

    # 检查点读写
    async def get_checkpoint(
        self,
        session_id: UUID,
        checkpoint_id: str,
    ) -> SessionCheckpoint | None:
        return await fetch_checkpoint(self._db, session_id, checkpoint_id)

    async def create_checkpoint(
        self,
        session_id: UUID,
        thread_ts: str,
        state: SessionRuntimeState,
        parent_ts: str | None,
    ) -> None:
        await persist_checkpoint(self._db, session_id, thread_ts, state, parent_ts)

    # 会话内资料查询
    async def list_chat_messages(self, session_id: UUID) -> list[RowMapping]:
        return await fetch_chat_messages(self._db, session_id)

    async def list_clues(self, session: StoredSession) -> list[RowMapping]:
        await apply_session_context(self._db, session)
        return await fetch_clues(self._db, session)

    async def list_evidences(self, session: StoredSession) -> list[RowMapping]:
        await apply_session_context(self._db, session)
        return await fetch_evidences(self._db, session)

    async def list_characters(self, session: StoredSession) -> list[RowMapping]:
        await apply_session_context(self._db, session)
        return await fetch_characters(self._db, session)

    async def list_character_chapters(self, session: StoredSession) -> list[RowMapping]:
        await apply_session_context(self._db, session)
        return await fetch_character_chapters(self._db, session)

    async def list_read_character_chapters(
        self,
        session: StoredSession,
    ) -> tuple[CharacterChapterAccess, ...]:
        await apply_session_context(self._db, session)
        return await fetch_read_character_chapters(self._db, session)

    async def get_character_chapter(
        self,
        session: StoredSession,
        chapter_id: str,
    ) -> CharacterChapterAccess | None:
        await apply_session_context(self._db, session)
        return await fetch_character_chapter(self._db, session, chapter_id)

    async def mark_evidence_viewed(
        self,
        session: StoredSession,
        evidence_id: str,
    ) -> ContentProgress | None:
        await apply_session_context(self._db, session)
        return await persist_content_viewed(
            self._db,
            session,
            "evidence",
            evidence_id,
            "viewed_evidences",
        )

    async def mark_character_chapter_read(
        self,
        session: StoredSession,
        chapter_id: str,
    ) -> ContentProgress | None:
        await apply_session_context(self._db, session)
        return await persist_content_viewed(
            self._db,
            session,
            "character_chapter",
            chapter_id,
            "read_character_chapters",
        )

    async def list_cards(self, session: StoredSession) -> list[RowMapping]:
        await apply_session_context(self._db, session)
        return await fetch_cards(self._db, session)

    async def get_review(self, session_id: UUID) -> RowMapping | None:
        return await fetch_review(self._db, session_id)

    async def stage_name(self, script_id: str, stage_id: str) -> str | None:
        return await fetch_stage_name(self._db, script_id, stage_id)


__all__ = [
    "CharacterChapterAccess",
    "ChatMessageDraft",
    "ContentProgress",
    "DiscoveryDraft",
    "SessionActionEffect",
    "SessionCheckpoint",
    "SessionRepository",
    "SessionRuntimeState",
    "StoredSession",
]
