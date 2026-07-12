"""公开游戏会话创建与查询端点。"""

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
    """从已发布剧本包创建游戏会话。

    Args:
        payload: 剧本包、玩家名称和必需的偏好角色 ID。
        current_user: 由鉴权依赖解析的可选 Supabase 身份。
        db: 请求作用域的异步数据库会话。

    Returns:
        已创建会话的标识符和初始运行时状态。

    Raises:
        ApiError: 认证或创建失败时抛出 `INVALID_TOKEN`、`INVALID_USER_ID` 或
            `SCRIPT_PACKAGE_NOT_FOUND`。
    """
    return await start_session(payload, current_user, db)


@router.get("/{session_id}", response_model=SessionStateResponse)
async def get_session(
    session_id: str,
    current_user: CurrentUserDep,
    db: SessionDep,
) -> SessionStateResponse:
    """返回可访问游戏会话的当前状态摘要。

    Args:
        session_id: 待加载会话的 UUID 字符串。
        current_user: 用于所有权检查的可选 Supabase 身份。
        db: 请求作用域的异步数据库会话。

    Returns:
        会话状态、阶段、场景、进度和可用动作。

    Raises:
        ApiError: 认证、解析或访问失败时抛出 `INVALID_TOKEN`、
            `INVALID_SESSION_ID`、`INVALID_USER_ID` 或 `SESSION_NOT_FOUND`。
    """
    return await get_session_state(session_id, current_user, db)


@router.patch("/{session_id}", response_model=UpdateSessionResponse)
async def update_session(
    session_id: str,
    payload: UpdateSessionRequest,
    current_user: CurrentUserDep,
    db: SessionDep,
) -> UpdateSessionResponse:
    """从已存储检查点恢复可访问的游戏会话。

    Args:
        session_id: 待恢复会话的 UUID 字符串。
        payload: 待恢复检查点的标识符。
        current_user: 用于所有权检查的可选 Supabase 身份。
        db: 请求作用域的异步数据库会话。

    Returns:
        恢复后的会话状态和检查点标识符。

    Raises:
        ApiError: 恢复失败时抛出 `INVALID_TOKEN`、`INVALID_SESSION_ID`、
            `INVALID_USER_ID`、`SESSION_NOT_FOUND` 或 `CHECKPOINT_NOT_FOUND`。
    """
    return await restore_session(session_id, payload, current_user, db)


# ── 会话内数据查询 ──


@router.get("/{session_id}/clues", response_model=ClueListResponse)
async def list_clues(
    session_id: str,
    current_user: CurrentUserDep,
    db: SessionDep,
) -> ClueListResponse:
    """列出可访问游戏会话中已解锁的线索。

    Args:
        session_id: 待查询会话的 UUID 字符串。
        current_user: 用于所有权检查的可选 Supabase 身份。
        db: 请求作用域的异步数据库会话。

    Returns:
        当前对会话玩家可见的线索。

    Raises:
        ApiError: 会话缺失或不可访问时抛出 `INVALID_TOKEN`、
            `INVALID_SESSION_ID`、`INVALID_USER_ID` 或 `SESSION_NOT_FOUND`。
    """
    return await get_clues(session_id, current_user, db)


@router.get("/{session_id}/evidences", response_model=EvidenceListResponse)
async def list_evidences(
    session_id: str,
    current_user: CurrentUserDep,
    db: SessionDep,
) -> EvidenceListResponse:
    """列出可访问游戏会话中已发现的证物。

    Args:
        session_id: 待查询会话的 UUID 字符串。
        current_user: 用于所有权检查的可选 Supabase 身份。
        db: 请求作用域的异步数据库会话。

    Returns:
        当前对会话玩家可见的证物记录。

    Raises:
        ApiError: 会话缺失或不可访问时抛出 `INVALID_TOKEN`、
            `INVALID_SESSION_ID`、`INVALID_USER_ID` 或 `SESSION_NOT_FOUND`。
    """
    return await get_evidences(session_id, current_user, db)


@router.get("/{session_id}/characters", response_model=CharacterListResponse)
async def list_characters(
    session_id: str,
    current_user: CurrentUserDep,
    db: SessionDep,
) -> CharacterListResponse:
    """列出可访问游戏会话中的剧本角色。

    Args:
        session_id: 待查询会话的 UUID 字符串。
        current_user: 用于所有权检查的可选 Supabase 身份。
        db: 请求作用域的异步数据库会话。

    Returns:
        剧本角色摘要；仅当剧本包没有已存储角色行时，回退到会话角色 ID。

    Raises:
        ApiError: 会话缺失或不可访问时抛出 `INVALID_TOKEN`、
            `INVALID_SESSION_ID`、`INVALID_USER_ID` 或 `SESSION_NOT_FOUND`。
    """
    return await get_characters(session_id, current_user, db)


@router.get("/{session_id}/chat-history", response_model=ChatHistoryResponse)
async def list_chat_history(
    session_id: str,
    current_user: CurrentUserDep,
    db: SessionDep,
) -> ChatHistoryResponse:
    """返回可访问游戏会话中已存储的聊天记录。

    Args:
        session_id: 待查询会话的 UUID 字符串。
        current_user: 用于所有权检查的可选 Supabase 身份。
        db: 请求作用域的异步数据库会话。

    Returns:
        会话已持久化的聊天消息。

    Raises:
        ApiError: 会话缺失或不可访问时抛出 `INVALID_TOKEN`、
            `INVALID_SESSION_ID`、`INVALID_USER_ID` 或 `SESSION_NOT_FOUND`。
    """
    return await get_chat_history(session_id, current_user, db)


@router.get("/{session_id}/cards", response_model=CardListResponse)
async def list_cards(
    session_id: str,
    current_user: CurrentUserDep,
    db: SessionDep,
) -> CardListResponse:
    """列出可访问游戏会话中的道具和技能卡证物。

    Args:
        session_id: 待查询会话的 UUID 字符串。
        current_user: 用于所有权检查的可选 Supabase 身份。
        db: 请求作用域的异步数据库会话。

    Returns:
        当前响应映射器映射为剩余一次使用且 `available=True` 的道具和技能卡证物行。

    Raises:
        ApiError: 会话缺失或不可访问时抛出 `INVALID_TOKEN`、
            `INVALID_SESSION_ID`、`INVALID_USER_ID` 或 `SESSION_NOT_FOUND`。
    """
    return await get_cards(session_id, current_user, db)


@router.get("/{session_id}/review", response_model=ReviewResponse)
async def get_review(
    session_id: str,
    current_user: CurrentUserDep,
    db: SessionDep,
) -> ReviewResponse:
    """返回可访问游戏会话的复盘表示。

    Args:
        session_id: 待查询会话的 UUID 字符串。
        current_user: 用于所有权检查的可选 Supabase 身份。
        db: 请求作用域的异步数据库会话。

    Returns:
        最新持久化复盘；不存在持久化复盘时，返回合成的零分 `N/A` 响应。

    Raises:
        ApiError: 会话缺失或不可访问时抛出 `INVALID_TOKEN`、
            `INVALID_SESSION_ID`、`INVALID_USER_ID` 或 `SESSION_NOT_FOUND`。
    """
    return await get_session_review(session_id, current_user, db)
