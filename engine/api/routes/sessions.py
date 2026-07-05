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
from engine.services.session_service import (
    get_cards_stub,
    get_characters_stub,
    get_chat_history_stub,
    get_clues_stub,
    get_evidences_stub,
    get_review_stub,
    get_session_stub,
    restore_session_stub,
    start_session_stub,
)

# ── 会话与数据查询路由 ──

router = APIRouter(prefix="/sessions", tags=["sessions"])


# ── 会话生命周期 ──


@router.post("", response_model=CreateSessionResponse)
async def create_session(
    payload: CreateSessionRequest,
    _current_user: CurrentUserDep,
) -> CreateSessionResponse:
    """Create a game session from a script package and preferred character."""
    return start_session_stub(payload)


@router.get("/{session_id}", response_model=SessionStateResponse)
async def get_session(
    session_id: str,
    _current_user: CurrentUserDep,
) -> SessionStateResponse:
    """Return the current session state summary used by the game shell."""
    return get_session_stub(session_id)


@router.patch("/{session_id}", response_model=UpdateSessionResponse)
async def update_session(
    session_id: str,
    payload: UpdateSessionRequest,
    _current_user: CurrentUserDep,
) -> UpdateSessionResponse:
    """Restore or maintain a session checkpoint."""
    return restore_session_stub(session_id, payload)


# ── 会话内数据查询 ──


@router.get("/{session_id}/clues", response_model=ClueListResponse)
async def list_clues(
    session_id: str,
    _current_user: CurrentUserDep,
) -> ClueListResponse:
    """Return clues unlocked for the current session."""
    return get_clues_stub(session_id)


@router.get("/{session_id}/evidences", response_model=EvidenceListResponse)
async def list_evidences(
    session_id: str,
    _current_user: CurrentUserDep,
) -> EvidenceListResponse:
    """Return evidences discovered in the current session."""
    return get_evidences_stub(session_id)


@router.get("/{session_id}/characters", response_model=CharacterListResponse)
async def list_characters(
    session_id: str,
    _current_user: CurrentUserDep,
) -> CharacterListResponse:
    """Return characters currently available in the active scene."""
    return get_characters_stub(session_id)


@router.get("/{session_id}/chat-history", response_model=ChatHistoryResponse)
async def list_chat_history(
    session_id: str,
    _current_user: CurrentUserDep,
) -> ChatHistoryResponse:
    """Return paginated chat history for a session."""
    return get_chat_history_stub(session_id)


@router.get("/{session_id}/cards", response_model=CardListResponse)
async def list_cards(
    session_id: str,
    _current_user: CurrentUserDep,
) -> CardListResponse:
    """Return usable skill and prop cards for a session."""
    return get_cards_stub(session_id)


@router.get("/{session_id}/review", response_model=ReviewResponse)
async def get_review(
    session_id: str,
    _current_user: CurrentUserDep,
) -> ReviewResponse:
    """Return the review and scoring result for a completed session."""
    return get_review_stub(session_id)
