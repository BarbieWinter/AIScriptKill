"""公开会话动作提交端点。"""

from fastapi import APIRouter

from engine.api.middleware.auth import CurrentUserDep
from engine.api.schemas import (
    ActionRequest,
    ActionResponse,
    FinalSubmissionRequest,
    SubmissionResult,
)
from engine.db.session import SessionDep
from engine.services.session_service import (
    perform_action as perform_session_action,
)
from engine.services.session_service import (
    submit_final as submit_final_submission,
)

# ── 游戏操作路由 ──

router = APIRouter(prefix="/sessions/{session_id}", tags=["actions"])


# ── 行动执行 ──


@router.post("/actions", response_model=ActionResponse)
async def perform_action(
    session_id: str,
    payload: ActionRequest,
    current_user: CurrentUserDep,
    db: SessionDep,
) -> ActionResponse:
    """对可访问会话执行一个真实 LangGraph 玩家动作。

    Args:
        session_id: 接收动作的会话 UUID 字符串。
        payload: 类型化动作名称和动作参数。
        current_user: 用于所有权检查的可选 Supabase 身份。
        db: 请求作用域的异步数据库会话。

    Returns:
        动作结果和面向客户端的效果。

    Raises:
        ApiError: 会话、剧本包缺失或动作被状态机拒绝时抛出稳定错误码，包括
            `INVALID_TOKEN`、`INVALID_SESSION_ID`、`INVALID_USER_ID`、
            `SESSION_NOT_FOUND`、`SCRIPT_PACKAGE_NOT_FOUND` 或核心动作错误。
    """
    return await perform_session_action(session_id, payload, current_user, db)


# ── 最终推理提交 ──


@router.post("/final-submission", response_model=SubmissionResult)
async def submit_final(
    session_id: str,
    payload: FinalSubmissionRequest,
    current_user: CurrentUserDep,
    db: SessionDep,
) -> SubmissionResult:
    """持久化并评分可访问会话的阶段判断。

    Args:
        session_id: 接收提交的会话 UUID 字符串。
        payload: A、B、C、D 中的一项确定性判断。
        current_user: 用于所有权检查的可选 Supabase 身份。
        db: 请求作用域的异步数据库会话。

    Returns:
        确定性分数和选定的结局结果。

    Raises:
        ApiError: 会话缺失或不可访问时抛出 `INVALID_TOKEN`、
            `INVALID_SESSION_ID`、`INVALID_USER_ID` 或 `SESSION_NOT_FOUND`。
    """
    return await submit_final_submission(session_id, payload, current_user, db)
