"""公开游戏会话创建与查询端点。"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Body, Query, Response, status

from engine.api.middleware.auth import (
    CurrentUserDep,
    VerifiedAnonymousPrincipalDep,
    require_verified_anonymous_principal,
)
from engine.api.schemas import (
    CardListResponse,
    CharacterChapterListResponse,
    CharacterChapterResponse,
    CharacterListResponse,
    ChatHistoryResponse,
    ClueListResponse,
    CommandReceiptResponse,
    CreateSessionRequest,
    CreateSessionResponse,
    EvidenceListResponse,
    EvidenceViewedResponse,
    ReviewResponse,
    SessionEventPage,
    SessionPresentationResponse,
    SessionStateResponse,
    UpdateSessionRequest,
    UpdateSessionResponse,
)
from engine.api.schemas.multiplayer_rooms import (
    AcceptRoomInviteResponse,
    CreateMultiplayerSessionRequest,
    CreateMultiplayerSessionResponse,
    CreateRoomInviteRequest,
    CreateRoomInviteResponse,
    CurrentMultiplayerSession,
    LobbySnapshotV1,
)
from engine.contracts.multiplayer_v1.commands import CommandResultV1, MultiplayerCommand
from engine.db.session import SessionDep
from engine.services.multiplayer_room_service import (
    accept_room_invite,
    create_multiplayer_session,
    create_room_invite,
    execute_lobby_command,
    get_current_multiplayer_session,
    get_lobby_snapshot,
    revoke_room_invite,
)
from engine.services.session_commands import (
    get_command_receipt,
    get_session_events,
)
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
invite_router = APIRouter(prefix="/session-invites", tags=["sessions"])


# ── 会话生命周期 ──


@router.post(
    "",
    response_model=CreateSessionResponse | CreateMultiplayerSessionResponse,
    responses={status.HTTP_201_CREATED: {"model": CreateMultiplayerSessionResponse}},
)
async def create_session(
    payload: Annotated[
        CreateSessionRequest | CreateMultiplayerSessionRequest,
        Body(),
    ],
    current_user: CurrentUserDep,
    db: SessionDep,
    response: Response,
) -> CreateSessionResponse | CreateMultiplayerSessionResponse:
    """保留 legacy 创建契约，并按严格 mode 分派 Multiplayer v1 创建。

    Args:
        payload: legacy 或带 ``mode=multiplayer_v1`` 的严格创建载荷。
        current_user: 可选 JWT 解析结果；多人分支必须是 verified anonymous identity。
        db: 请求作用域数据库会话。
        response: 用于仅把 multiplayer 创建响应设为 201 的 FastAPI response。

    Returns:
        对应模式的已创建会话响应。

    Raises:
        ApiError: 身份、feature gate、剧本包或未完成房间约束不满足。
    """

    if isinstance(payload, CreateMultiplayerSessionRequest):
        principal = await require_verified_anonymous_principal(current_user)
        created = await create_multiplayer_session(payload, principal, db)
        response.status_code = status.HTTP_201_CREATED
        return created
    return await start_session(payload, current_user, db)


@router.get("/current", response_model=CurrentMultiplayerSession | None)
async def get_current_room(
    principal: VerifiedAnonymousPrincipalDep,
    db: SessionDep,
) -> CurrentMultiplayerSession | None:
    """返回当前 anonymous principal 的未完成多人房间定位器。

    Args:
        principal: 经过验证的 anonymous principal。
        db: 请求作用域数据库会话。

    Returns:
        当前 lobby/active 定位器，或没有 reservation 时返回 null。

    Raises:
        ApiError: 身份无效或 multiplayer feature 被禁用。
    """

    return await get_current_multiplayer_session(principal, db)


@invite_router.post("/{token}/accept", response_model=AcceptRoomInviteResponse)
async def accept_invite(
    token: str,
    principal: VerifiedAnonymousPrincipalDep,
    db: SessionDep,
) -> AcceptRoomInviteResponse:
    """使用一次性明文 token 加入房间；token 本身不授予任何读取权限。"""

    return await accept_room_invite(token, principal, db)


@router.post(
    "/{session_id}/invites",
    response_model=CreateRoomInviteResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_invite(
    session_id: str,
    payload: CreateRoomInviteRequest,
    principal: VerifiedAnonymousPrincipalDep,
    db: SessionDep,
) -> CreateRoomInviteResponse:
    """由 lobby 房主创建短时邀请，并仅在此响应返回一次明文 token。

    Args:
        session_id: 多人房间 UUID。
        payload: 受限的邀请 TTL。
        principal: 经过验证的 anonymous principal。
        db: 请求作用域数据库会话。

    Returns:
        新邀请 ID、一次性 token 和数据库时间派生的 expiry。

    Raises:
        ApiError: 房间、成员、房主、容量或 feature gate 校验失败。
    """

    return await create_room_invite(session_id, payload, principal, db)


@router.delete(
    "/{session_id}/invites/{invite_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def revoke_invite(
    session_id: str,
    invite_id: str,
    principal: VerifiedAnonymousPrincipalDep,
    db: SessionDep,
) -> Response:
    """由房主撤销邀请；重复撤销保持 204 且不推进 revision。

    Args:
        session_id: 多人房间 UUID。
        invite_id: 待撤销邀请 UUID。
        principal: 经过验证的 anonymous principal。
        db: 请求作用域数据库会话。

    Returns:
        无响应体的 204 响应。

    Raises:
        ApiError: 房间、邀请、成员、房主或 feature gate 校验失败。
    """

    await revoke_room_invite(session_id, invite_id, principal, db)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{session_id}/snapshot", response_model=LobbySnapshotV1)
async def get_room_snapshot(
    session_id: str,
    principal: VerifiedAnonymousPrincipalDep,
    db: SessionDep,
) -> LobbySnapshotV1:
    """返回不含 principal、token、package 定义或私有章节的安全房间投影。

    Args:
        session_id: 多人房间 UUID。
        principal: 经过验证的 anonymous principal。
        db: 请求作用域数据库会话。

    Returns:
        仅供房间成员读取的 participant-safe lobby/active 投影。

    Raises:
        ApiError: 房间、成员、固定 package 或 feature gate 校验失败。
    """

    return await get_lobby_snapshot(session_id, principal, db)


@router.post("/{session_id}/commands", response_model=CommandResultV1)
async def post_room_command(
    session_id: str,
    command: MultiplayerCommand,
    principal: VerifiedAnonymousPrincipalDep,
    db: SessionDep,
) -> CommandResultV1:
    """解析完整多人命令 union，并仅执行 MP-2 lobby 命令。

    Args:
        session_id: 多人房间 UUID。
        command: 完整 ``MultiplayerCommand`` 严格 discriminated union。
        principal: 经过验证的 anonymous principal。
        db: 请求作用域数据库会话。

    Returns:
        MP-2 非持久幂等的 accepted command result。

    Raises:
        ApiError: 非大厅命令、revision、权限、状态或 feature gate 校验失败。
    """

    return await execute_lobby_command(session_id, command, principal, db)


@router.get(
    "/{session_id}/commands/{command_id}",
    response_model=CommandReceiptResponse,
)
async def get_receipt(
    session_id: str,
    command_id: UUID,
    current_user: CurrentUserDep,
    db: SessionDep,
) -> CommandReceiptResponse:
    """Return one durable command receipt for an authorized session.

    Args:
        session_id: UUID string identifying the session.
        command_id: Client command identity to replay.
        current_user: Authenticated session principal.
        db: Request-scoped asynchronous database session.

    Returns:
        The stored receipt and its terminal or processing state.

    Raises:
        ApiError: Raises ``SESSION_NOT_FOUND`` or ``COMMAND_NOT_FOUND`` when access
            or the requested receipt fails.
    """
    return await get_command_receipt(session_id, command_id, current_user, db)


@router.get("/{session_id}/events", response_model=SessionEventPage)
async def list_events(
    session_id: str,
    current_user: CurrentUserDep,
    db: SessionDep,
    after_sequence: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
) -> SessionEventPage:
    """Return ordered public events and an authoritative HTTP snapshot.

    Args:
        session_id: UUID string identifying the session.
        current_user: Authenticated session principal.
        db: Request-scoped asynchronous database session.
        after_sequence: Exclusive event cursor, starting at zero.
        limit: Maximum number of events to return, from 1 through 500.

    Returns:
        A participant-safe snapshot, ordered events, and the next cursor.

    Raises:
        ApiError: Raises ``SESSION_NOT_FOUND``, ``INVALID_EVENT_CURSOR`` or
            ``INVALID_EVENT_LIMIT`` for inaccessible or invalid requests.
    """
    return await get_session_events(
        session_id,
        after_sequence,
        limit,
        current_user,
        db,
    )


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
