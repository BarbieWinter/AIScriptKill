"""公开游戏会话创建与查询端点。"""

from fastapi import APIRouter

from engine.api.middleware.auth import CurrentUserDep
from engine.api.schemas import (
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
    ReviewResponse,
    SessionPresentationResponse,
    SessionStateResponse,
    UpdateSessionRequest,
    UpdateSessionResponse,
)
from engine.db.session import SessionDep
from engine.services.session_service import (
    get_cards,
    get_character_chapters,
    get_characters,
    get_chat_history,
    get_clues,
    get_evidences,
    get_session_presentation,
    read_character_chapter,
    restore_session,
    start_session,
    view_evidence,
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


@router.get(
    "/{session_id}/presentation",
    response_model=SessionPresentationResponse,
)
async def get_presentation(
    session_id: str,
    current_user: CurrentUserDep,
    db: SessionDep,
) -> SessionPresentationResponse:
    """返回可访问会话当前阶段和场景的防剧透展示投影。

    Args:
        session_id: 待展示会话的 UUID 字符串。
        current_user: 用于所有权检查的可选 Supabase 身份。
        db: 请求作用域的异步数据库会话。

    Returns:
        已发布运行时包中的当前阶段、当前场景、公开热点和可选判断题。

    Raises:
        ApiError: 认证、会话、已发布剧本包、当前阶段或当前场景不可用时抛出
            `INVALID_TOKEN`、`INVALID_SESSION_ID`、`INVALID_USER_ID`、
            `SESSION_NOT_FOUND`、`SCRIPT_PACKAGE_NOT_FOUND` 或
            `SESSION_PRESENTATION_NOT_FOUND`。
    """
    return await get_session_presentation(session_id, current_user, db)


@router.patch("/{session_id}", response_model=UpdateSessionResponse)
async def update_session(
    session_id: str,
    payload: UpdateSessionRequest,
    current_user: CurrentUserDep,
    db: SessionDep,
) -> UpdateSessionResponse:
    """保留当前已禁用的 legacy 会话恢复维护入口。

    Args:
        session_id: legacy 维护请求中的会话 UUID 字符串。
        payload: 保留的 legacy 恢复请求载荷。
        current_user: 由鉴权依赖解析的可选 Supabase 身份。
        db: 请求作用域的异步数据库会话；当前禁用路径不会访问它。

    Returns:
        当前不会返回；响应模型仅为 legacy wire contract 保留。

    Raises:
        ApiError: 令牌或会话 ID 无效时抛出 `INVALID_TOKEN` 或
            `INVALID_SESSION_ID`；合法 UUID 稳定抛出 `SESSION_RESTORE_UNAVAILABLE`。
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


@router.post(
    "/{session_id}/evidences/{evidence_id}/viewed",
    response_model=EvidenceViewedResponse,
)
async def mark_evidence_viewed(
    session_id: str,
    evidence_id: str,
    current_user: CurrentUserDep,
    db: SessionDep,
) -> EvidenceViewedResponse:
    """将可访问会话中已发现的证物单调升级为已查看。

    Args:
        session_id: 待更新会话的 UUID 字符串。
        evidence_id: 已由当前会话发现的证物 ID。
        current_user: 用于所有权检查的可选 Supabase 身份。
        db: 请求作用域的异步数据库会话。

    Returns:
        已查看证物的标识符和不会降级的持久化状态。

    Raises:
        ApiError: 会话或证物不可访问时抛出 `INVALID_TOKEN`、
            `INVALID_SESSION_ID`、`INVALID_USER_ID`、`SESSION_NOT_FOUND` 或
            `EVIDENCE_NOT_DISCOVERED`。
    """
    return await view_evidence(session_id, evidence_id, current_user, db)


@router.get(
    "/{session_id}/character-chapters",
    response_model=CharacterChapterListResponse,
)
async def list_character_chapters(
    session_id: str,
    current_user: CurrentUserDep,
    db: SessionDep,
) -> CharacterChapterListResponse:
    """列出可访问会话中当前玩家角色已解锁的人物章节。

    Args:
        session_id: 待查询会话的 UUID 字符串。
        current_user: 用于所有权检查的可选 Supabase 身份。
        db: 请求作用域的异步数据库会话。

    Returns:
        仅包含当前玩家角色且已有会话授权的章节目录。

    Raises:
        ApiError: 会话不可访问时抛出 `INVALID_TOKEN`、`INVALID_SESSION_ID`、
            `INVALID_USER_ID` 或 `SESSION_NOT_FOUND`。
    """
    return await get_character_chapters(session_id, current_user, db)


@router.get(
    "/{session_id}/character-chapters/{chapter_id}",
    response_model=CharacterChapterResponse,
)
async def get_character_chapter(
    session_id: str,
    chapter_id: str,
    current_user: CurrentUserDep,
    db: SessionDep,
) -> CharacterChapterResponse:
    """读取当前玩家角色已解锁的人物章节并持久化已读状态。

    Args:
        session_id: 待查询会话的 UUID 字符串。
        chapter_id: 已由当前会话授权的人物章节 ID。
        current_user: 用于所有权检查的可选 Supabase 身份。
        db: 请求作用域的异步数据库会话。

    Returns:
        经角色归属和会话授权过滤的章节元数据与 Markdown 正文。

    Raises:
        ApiError: 会话或章节不可访问时抛出 `INVALID_TOKEN`、
            `INVALID_SESSION_ID`、`INVALID_USER_ID`、`SESSION_NOT_FOUND` 或
            `CHARACTER_CHAPTER_NOT_FOUND`。
    """
    return await read_character_chapter(session_id, chapter_id, current_user, db)


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
