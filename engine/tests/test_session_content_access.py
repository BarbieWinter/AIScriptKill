from datetime import UTC, datetime
from typing import cast
from uuid import UUID

from sqlalchemy.dialects import postgresql
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncSession

from engine.repositories.session_models import SessionRuntimeState, StoredSession
from engine.repositories.session_mutations import mark_content_viewed
from engine.repositories.session_queries import (
    get_character_chapter,
    list_character_chapters,
    list_read_character_chapters,
)
from engine.services.query_mappers import evidences_response

SESSION_ID = UUID("00000000-0000-0000-0000-000000000111")


def _stored_session() -> StoredSession:
    now = datetime.now(UTC)
    return StoredSession(
        id=SESSION_ID,
        script_id="snow-village",
        player_id=None,
        player_character_id="zhuosiyuan",
        state=SessionRuntimeState(
            unlocked_character_chapters=["chapter-01"],
            discovered_evidences=["back-door-image"],
        ),
        status="in_progress",
        created_at=now,
        updated_at=now,
    )


async def test_character_chapter_queries_scope_content_to_session_player() -> None:
    db = _RecordingDb(
        mapping_rows=[
            {
                "chapter_id": "chapter-01",
                "character_id": "zhuosiyuan",
                "sort_order": 1,
                "title": "炉火未熄",
                "status": "unlocked",
            }
        ]
    )
    session = _stored_session()

    rows = await list_character_chapters(_async_session(db), session)

    assert rows[0]["chapter_id"] == "chapter-01"
    sql = _compiled_sql(db.statements[0])
    assert "script_character_chapters.script_id = 'snow-village'" in sql
    assert "script_character_chapters.character_id = 'zhuosiyuan'" in sql
    assert f"session_discoveries.session_id = '{SESSION_ID}'" in sql
    assert "session_discoveries.entity_type = 'character_chapter'" in sql
    assert "session_discoveries.status IN ('unlocked', 'viewed')" in sql
    assert "script_character_chapters.content" not in sql


async def test_character_chapter_read_query_projects_content_after_authorization() -> None:
    db = _RecordingDb(
        mapping_row={
            "chapter_id": "chapter-01",
            "character_id": "zhuosiyuan",
            "sort_order": 1,
            "title": "炉火未熄",
            "content": "章节正文",
            "status": "unlocked",
        }
    )
    session = _stored_session()

    chapter = await get_character_chapter(
        _async_session(db),
        session,
        "chapter-01",
    )

    assert chapter is not None
    assert chapter.content == "章节正文"
    sql = _compiled_sql(db.statements[0])
    assert "script_character_chapters.chapter_id = 'chapter-01'" in sql
    assert "script_character_chapters.content" in sql
    assert "script_character_chapters.character_id = 'zhuosiyuan'" in sql


async def test_dialogue_chapter_corpus_requires_explicit_read_status() -> None:
    db = _RecordingDb(
        mapping_rows=[
            {
                "chapter_id": "chapter-01",
                "character_id": "zhuosiyuan",
                "sort_order": 1,
                "title": "炉火未熄",
                "content": "章节正文",
                "status": "viewed",
            }
        ]
    )

    chapters = await list_read_character_chapters(_async_session(db), _stored_session())

    assert chapters[0].content == "章节正文"
    sql = _compiled_sql(db.statements[0])
    assert "session_discoveries.status = 'viewed'" in sql
    assert "script_character_chapters.character_id = 'zhuosiyuan'" in sql


async def test_evidence_response_projects_persisted_presentation_targets() -> None:
    rows = cast(
        list[RowMapping],
        [
            {
                "evidence_id": "back-door-image",
                "name": "21:13 后门截图",
                "image_url": "https://example.test/back-door.svg",
                "description_surface": "后门半开，影子不可辨认。",
                "status": "viewed",
            }
        ],
    )

    response = evidences_response(
        rows,
        [
            {"evidence_id": "back-door-image", "character_id": "wangdada"},
            {"evidence_id": "other", "character_id": "chengjun"},
        ],
    )

    assert response.evidences[0].shown_to_characters == ["wangdada"]


async def test_viewed_mutation_is_scoped_monotonic_and_commits_once() -> None:
    db = _RecordingDb(
        scalars=[_stored_session().state.model_dump(mode="json")],
        mapping_row={"entity_id": "back-door-image", "status": "deep_viewed"},
    )
    session = _stored_session()

    progress = await mark_content_viewed(
        _async_session(db),
        session,
        "evidence",
        "back-door-image",
        "viewed_evidences",
    )

    assert progress is not None
    assert progress.status == "deep_viewed"
    assert db.commits == 1
    discovery_sql = _compiled_sql(db.statements[1])
    assert f"session_discoveries.session_id = '{SESSION_ID}'" in discovery_sql
    assert "session_discoveries.entity_type = 'evidence'" in discovery_sql
    assert "session_discoveries.entity_id = 'back-door-image'" in discovery_sql
    assert "WHEN (session_discoveries.status = 'unlocked') THEN 'viewed'" in discovery_sql
    assert "ELSE session_discoveries.status" in discovery_sql
    state_statement = db.statements[2]
    state_sql = str(state_statement.compile(dialect=postgresql.dialect()))  # type: ignore[attr-defined]
    assert "UPDATE game_sessions SET state=" in state_sql
    state_parameters = state_statement.compile(dialect=postgresql.dialect()).params  # type: ignore[attr-defined]
    assert state_parameters["state"]["viewed_evidences"] == ["back-door-image"]


async def test_viewed_mutation_does_not_create_undiscovered_content() -> None:
    db = _RecordingDb(
        scalars=[_stored_session().state.model_dump(mode="json")],
        mapping_row=None,
    )

    progress = await mark_content_viewed(
        _async_session(db),
        _stored_session(),
        "character_chapter",
        "chapter-02",
        "read_character_chapters",
    )

    assert progress is None
    assert len(db.statements) == 2
    assert db.commits == 0


class _RecordingDb:
    def __init__(
        self,
        *,
        mapping_rows: list[RowMapping | dict[str, object]] | None = None,
        mapping_row: RowMapping | dict[str, object] | None = None,
        scalars: list[object] | None = None,
    ) -> None:
        self.statements: list[object] = []
        self.commits = 0
        self._mapping_rows = mapping_rows or []
        self._mapping_row = mapping_row
        self._scalars = list(scalars or [])

    async def execute(self, statement: object) -> "_Result":
        self.statements.append(statement)
        scalar = self._scalars.pop(0) if self._scalars else None
        return _Result(self._mapping_rows, self._mapping_row, scalar)

    async def commit(self) -> None:
        self.commits += 1


class _Result:
    def __init__(
        self,
        rows: list[RowMapping | dict[str, object]],
        row: RowMapping | dict[str, object] | None,
        scalar: object,
    ) -> None:
        self._rows = rows
        self._row = row
        self._scalar = scalar

    def mappings(self) -> "_Result":
        return self

    def all(self) -> list[RowMapping | dict[str, object]]:
        return self._rows

    def one_or_none(self) -> RowMapping | dict[str, object] | None:
        return self._row

    def scalar_one_or_none(self) -> object:
        return self._scalar


def _async_session(db: "_RecordingDb") -> AsyncSession:
    return cast(AsyncSession, cast(object, db))


def _compiled_sql(statement: object) -> str:
    return str(
        statement.compile(  # type: ignore[attr-defined]
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )
