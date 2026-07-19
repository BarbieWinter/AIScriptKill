from sqlalchemy import select
from sqlalchemy.engine import RowMapping

from engine.db.tables import game_sessions
from engine.repositories.session_models import SessionRuntimeState, StoredSession

# ── game_sessions 行映射 ──

SESSION_COLUMNS = (
    game_sessions.c.id,
    game_sessions.c.script_id,
    game_sessions.c.player_id,
    game_sessions.c.player_character_id,
    game_sessions.c.state,
    game_sessions.c.status,
    game_sessions.c.mode,
    game_sessions.c.revision,
    game_sessions.c.event_head_sequence,
    game_sessions.c.created_at,
    game_sessions.c.updated_at,
)


def session_select():
    return select(*SESSION_COLUMNS)


# ── 行到领域模型 ──


def stored_session_from_row(row: RowMapping) -> StoredSession:
    return StoredSession(
        id=row["id"],
        script_id=row["script_id"],
        player_id=row["player_id"],
        player_character_id=row["player_character_id"],
        state=SessionRuntimeState.model_validate(row["state"]),
        status=row["status"],
        mode=row["mode"],
        revision=int(row["revision"] or 0),
        event_head_sequence=int(row["event_head_sequence"] or 0),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )
