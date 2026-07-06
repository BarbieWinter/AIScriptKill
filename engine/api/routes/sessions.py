from fastapi import APIRouter

from engine.api.middleware.auth import CurrentUserDep
from engine.api.schemas import (
    CardListResponse,
    CharacterListResponse,
    ChatHistoryResponse,
    ClueListResponse,
    CreateSessionRequest,
    CreateSessionResponse,
    EvidenceListResponse,
    ReviewResponse,
    SessionStateResponse,
    UpdateSessionRequest,
    UpdateSessionResponse,
)
from engine.db.session import SessionDep
from engine.services.session_service import (
    get_cards,
    get_characters,
    get_chat_history,
    get_clues,
    get_evidences,
    restore_session,
    start_session,
)
from engine.services.session_service import (
    get_review as get_session_review,
)
from engine.services.session_service import (
    get_session as get_session_state,
)

# ── 会话与数据查询路由 ──

router = APIRouter(prefix="/sessions", tags=["sessions"])


# ── 会话生命周期 ──


@router.post("", response_model=CreateSessionResponse)
async def create_session(
    payload: CreateSessionRequest,
    current_user: CurrentUserDep,
    db: SessionDep,
) -> CreateSessionResponse:
    """Create a game session from a script package and preferred character."""
    return await start_session(payload, current_user, db)


@router.get("/{session_id}", response_model=SessionStateResponse)
async def get_session(
    session_id: str,
    current_user: CurrentUserDep,
    db: SessionDep,
) -> SessionStateResponse:
    """Return the current session state summary used by the game shell."""
    return await get_session_state(session_id, current_user, db)


@router.patch("/{session_id}", response_model=UpdateSessionResponse)
async def update_session(
    session_id: str,
    payload: UpdateSessionRequest,
    current_user: CurrentUserDep,
    db: SessionDep,
) -> UpdateSessionResponse:
    """Restore or maintain a session checkpoint."""
    return await restore_session(session_id, payload, current_user, db)


# ── 会话内数据查询 ──


@router.get("/{session_id}/clues", response_model=ClueListResponse)
async def list_clues(
    session_id: str,
    current_user: CurrentUserDep,
    db: SessionDep,
) -> ClueListResponse:
    """Return clues unlocked for the current session."""
    return await get_clues(session_id, current_user, db)


@router.get("/{session_id}/evidences", response_model=EvidenceListResponse)
async def list_evidences(
    session_id: str,
    current_user: CurrentUserDep,
    db: SessionDep,
) -> EvidenceListResponse:
    """Return evidences discovered in the current session."""
    return await get_evidences(session_id, current_user, db)


@router.get("/{session_id}/characters", response_model=CharacterListResponse)
async def list_characters(
    session_id: str,
    current_user: CurrentUserDep,
    db: SessionDep,
) -> CharacterListResponse:
    """Return characters currently available in the active scene."""
    return await get_characters(session_id, current_user, db)


@router.get("/{session_id}/chat-history", response_model=ChatHistoryResponse)
async def list_chat_history(
    session_id: str,
    current_user: CurrentUserDep,
    db: SessionDep,
) -> ChatHistoryResponse:
    """Return paginated chat history for a session."""
    return await get_chat_history(session_id, current_user, db)


@router.get("/{session_id}/cards", response_model=CardListResponse)
async def list_cards(
    session_id: str,
    current_user: CurrentUserDep,
    db: SessionDep,
) -> CardListResponse:
    """Return usable skill and prop cards for a session."""
    return await get_cards(session_id, current_user, db)


@router.get("/{session_id}/review", response_model=ReviewResponse)
async def get_review(
    session_id: str,
    current_user: CurrentUserDep,
    db: SessionDep,
) -> ReviewResponse:
    """Return the review and scoring result for a completed session."""
    return await get_session_review(session_id, current_user, db)
