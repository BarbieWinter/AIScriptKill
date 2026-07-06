from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from engine.api.errors import bad_request, not_found
from engine.api.middleware.auth import CurrentUser
from engine.api.schemas import (
    ActionRequest,
    ActionResponse,
    CardListResponse,
    CharacterListResponse,
    ChatHistoryResponse,
    ClueListResponse,
    CreateSessionRequest,
    CreateSessionResponse,
    EvidenceListResponse,
    FinalSubmissionRequest,
    ReviewResponse,
    SessionStateResponse,
    SubmissionResult,
    UpdateSessionRequest,
    UpdateSessionResponse,
)
from engine.repositories.session_repository import SessionRepository, StoredSession
from engine.services.session_mappers import (
    action_response_and_effect,
    cards_response,
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
    response, effect = action_response_and_effect(payload)
    await repository.apply_action(session, effect)
    return response


async def submit_final(
    session_id: str,
    payload: FinalSubmissionRequest,
    current_user: CurrentUser,
    db: AsyncSession,
) -> SubmissionResult:
    repository = SessionRepository(db)
    session = await _load_session(repository, session_id, current_user)
    result = final_submission_result(payload)
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
    return evidences_response(await repository.list_evidences(session))


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
