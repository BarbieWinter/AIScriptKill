from typing import Final

from sqlalchemy import TextClause, text
from sqlalchemy.ext.asyncio import AsyncSession

from engine.repositories.session_models import StoredSession

# ── RLS 会话上下文 ──

RUNTIME_CONTEXT_SQL: Final[TextClause] = text(
    """
    select
        set_config('app.current_stage', :current_stage, true),
        set_config('app.player_character', :player_character, true)
    """,
)


async def apply_session_context(db: AsyncSession, session: StoredSession) -> None:
    await db.execute(
        RUNTIME_CONTEXT_SQL,
        {
            "current_stage": session.state.current_stage,
            "player_character": session.player_character_id,
        },
    )
