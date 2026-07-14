from collections.abc import Mapping
from typing import cast
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from engine.api.errors import bad_request, not_found
from engine.api.middleware.auth import CurrentUser
from engine.api.schemas import (
    ActionRequest,
    ActionResponse,
    CardListResponse,
    CharacterChapterListResponse,
    CharacterChapterResponse,
    CharacterListResponse,
    ChatHistoryResponse,
    ClueListResponse,
    CreateSessionRequest,
    CreateSessionResponse,
    EvidenceListResponse,
    EvidenceViewedResponse,
    FinalSubmissionRequest,
    ReviewResponse,
    SessionStateResponse,
    SubmissionResult,
    UpdateSessionRequest,
    UpdateSessionResponse,
)
from engine.repositories.runtime_package_repository import get_runtime_package
from engine.repositories.session_repository import (
    CharacterChapterAccess,
    SessionRepository,
    StoredSession,
)
from engine.services.runtime_session import create_runtime_action_executor
from engine.services.session_mappers import (
    cards_response,
    character_chapter_response,
    character_chapters_response,
    characters_response,
    chat_history_response,
    clues_response,
    create_response,
    evidences_response,
    final_submission_result,
    restore_response,
    review_response,
    state_response,
    submission_result_payload,
)

# ── 会话生命周期 ──


async def start_session(
    payload: CreateSessionRequest,
    current_user: CurrentUser,
    db: AsyncSession,
) -> CreateSessionResponse:
    repository = SessionRepository(db)
    session = await repository.create_session(payload, _player_id(current_user))
    if session is None:
        raise not_found("SCRIPT_PACKAGE_NOT_FOUND", "未找到可用于开局的已发布剧本包")
    return create_response(session)


async def get_session(
    session_id: str,
    current_user: CurrentUser,
    db: AsyncSession,
) -> SessionStateResponse:
    repository = SessionRepository(db)
    session = await _load_session(repository, session_id, current_user)
    stage_name = await repository.stage_name(session.script_id, session.state.current_stage)
    return state_response(session, stage_name)


async def restore_session(
    session_id: str,
    payload: UpdateSessionRequest,
    current_user: CurrentUser,
    db: AsyncSession,
) -> UpdateSessionResponse:
    repository = SessionRepository(db)
    session = await _load_session(repository, session_id, current_user)
    restored = await repository.restore_checkpoint(session.id, payload.checkpoint_id)
    if restored is None:
        raise not_found("CHECKPOINT_NOT_FOUND", "未找到指定会话检查点")
    return restore_response(restored, payload.checkpoint_id)


# ── 游戏行动与最终提交 ──


async def perform_action(
    session_id: str,
    payload: ActionRequest,
    current_user: CurrentUser,
    db: AsyncSession,
) -> ActionResponse:
    repository = SessionRepository(db)
    session = await _load_session(repository, session_id, current_user)
    return await create_runtime_action_executor().execute(session, payload, db)


async def submit_final(
    session_id: str,
    payload: FinalSubmissionRequest,
    current_user: CurrentUser,
    db: AsyncSession,
) -> SubmissionResult:
    repository = SessionRepository(db)
    session = await _load_session(repository, session_id, current_user)
    if session.script_id != "snow-village":
        raise bad_request(
            "JUDGMENT_UNAVAILABLE",
            "当前剧本包尚未提供阶段判断。",
        )
    if session.state.current_stage != "back_door_judgement":
        raise bad_request(
            "JUDGMENT_NOT_AVAILABLE",
            "只有进入后门判断阶段后才能提交判断。",
        )
    package = await get_runtime_package(db, session.script_id)
    if package is None:
        raise not_found("SCRIPT_PACKAGE_NOT_FOUND", "未找到会话对应的已发布剧本包")
    stage = next(
        (item for item in package.stages if item.id == session.state.current_stage),
        None,
    )
    if stage is None:
        raise bad_request("JUDGMENT_UNAVAILABLE", "当前阶段没有可提交的判断。")
    correct_option = _judgment_correct_option(stage.definition)
    if correct_option is None:
        raise bad_request("JUDGMENT_UNAVAILABLE", "当前阶段没有可提交的判断。")
    result = final_submission_result(payload, correct_option=correct_option)
    await repository.save_final_submission(
        session,
        payload,
        submission_result_payload(result),
        result.score,
    )
    return result


# ── 会话内数据查询 ──


async def get_clues(
    session_id: str,
    current_user: CurrentUser,
    db: AsyncSession,
) -> ClueListResponse:
    repository = SessionRepository(db)
    session = await _load_session(repository, session_id, current_user)
    return clues_response(await repository.list_clues(session))


async def get_evidences(
    session_id: str,
    current_user: CurrentUser,
    db: AsyncSession,
) -> EvidenceListResponse:
    repository = SessionRepository(db)
    session = await _load_session(repository, session_id, current_user)
    rows = await repository.list_evidences(session)
    return evidences_response(rows, session.state.evidences_shown_to_npcs)


async def view_evidence(
    session_id: str,
    evidence_id: str,
    current_user: CurrentUser,
    db: AsyncSession,
) -> EvidenceViewedResponse:
    repository = SessionRepository(db)
    session = await _load_session(repository, session_id, current_user)
    progress = await repository.mark_evidence_viewed(session, evidence_id)
    if progress is None:
        raise not_found("EVIDENCE_NOT_DISCOVERED", "未找到当前会话已发现的指定证物")
    return EvidenceViewedResponse(evidence_id=progress.entity_id, status=progress.status)


async def get_character_chapters(
    session_id: str,
    current_user: CurrentUser,
    db: AsyncSession,
) -> CharacterChapterListResponse:
    repository = SessionRepository(db)
    session = await _load_session(repository, session_id, current_user)
    return character_chapters_response(await repository.list_character_chapters(session))


async def read_character_chapter(
    session_id: str,
    chapter_id: str,
    current_user: CurrentUser,
    db: AsyncSession,
) -> CharacterChapterResponse:
    repository = SessionRepository(db)
    session = await _load_session(repository, session_id, current_user)
    chapter = await repository.get_character_chapter(session, chapter_id)
    if chapter is None:
        raise not_found("CHARACTER_CHAPTER_NOT_FOUND", "未找到当前角色已解锁的指定章节")
    progress = await repository.mark_character_chapter_read(session, chapter_id)
    if progress is None:
        raise not_found("CHARACTER_CHAPTER_NOT_FOUND", "未找到当前角色已解锁的指定章节")
    return character_chapter_response(
        CharacterChapterAccess(
            chapter_id=chapter.chapter_id,
            character_id=chapter.character_id,
            sort_order=chapter.sort_order,
            title=chapter.title,
            content=chapter.content,
            status=progress.status,
        )
    )


async def get_characters(
    session_id: str,
    current_user: CurrentUser,
    db: AsyncSession,
) -> CharacterListResponse:
    repository = SessionRepository(db)
    session = await _load_session(repository, session_id, current_user)
    rows = await repository.list_characters(session)
    return characters_response(rows, session.state.available_characters)


async def get_chat_history(
    session_id: str,
    current_user: CurrentUser,
    db: AsyncSession,
) -> ChatHistoryResponse:
    repository = SessionRepository(db)
    session = await _load_session(repository, session_id, current_user)
    return chat_history_response(await repository.list_chat_messages(session.id))


async def get_cards(
    session_id: str,
    current_user: CurrentUser,
    db: AsyncSession,
) -> CardListResponse:
    repository = SessionRepository(db)
    session = await _load_session(repository, session_id, current_user)
    return cards_response(await repository.list_cards(session))


async def get_review(
    session_id: str,
    current_user: CurrentUser,
    db: AsyncSession,
) -> ReviewResponse:
    repository = SessionRepository(db)
    session = await _load_session(repository, session_id, current_user)
    return review_response(session, await repository.get_review(session.id))


# ── 标识解析与加载辅助 ──


def _judgment_correct_option(definition: Mapping[str, object]) -> str | None:
    special_rules = definition.get("special_rules")
    if not isinstance(special_rules, Mapping):
        return None
    special_rules_mapping = cast(Mapping[object, object], special_rules)
    judgement = special_rules_mapping.get("judgement")
    if not isinstance(judgement, Mapping):
        return None
    judgement_mapping = cast(Mapping[object, object], judgement)
    correct_option = judgement_mapping.get("correct_option")
    if correct_option not in ("A", "B", "C", "D"):
        return None
    return str(correct_option)


async def _load_session(
    repository: SessionRepository,
    session_id: str,
    current_user: CurrentUser,
) -> StoredSession:
    session = await repository.get_session(_session_uuid(session_id))
    if session is None:
        raise not_found("SESSION_NOT_FOUND", "未找到指定游戏会话")
    _assert_session_access(session, current_user)
    return session


def _session_uuid(session_id: str) -> UUID:
    try:
        return UUID(session_id)
    except ValueError as exc:
        raise bad_request("INVALID_SESSION_ID", "session_id 必须是 UUID") from exc


def _player_id(current_user: CurrentUser) -> UUID | None:
    if current_user.role == "anonymous":
        return None
    try:
        return UUID(current_user.subject)
    except ValueError as exc:
        raise bad_request("INVALID_USER_ID", "Supabase 用户 ID 必须是 UUID") from exc


def _assert_session_access(session: StoredSession, current_user: CurrentUser) -> None:
    if session.player_id is None:
        return
    if _player_id(current_user) == session.player_id:
        return
    raise not_found("SESSION_NOT_FOUND", "未找到指定游戏会话")
