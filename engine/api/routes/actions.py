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
    """Route a player action into the game engine action pipeline."""
    return await perform_session_action(session_id, payload, current_user, db)


# ── 最终推理提交 ──


@router.post("/final-submission", response_model=SubmissionResult)
async def submit_final(
    session_id: str,
    payload: FinalSubmissionRequest,
    current_user: CurrentUserDep,
    db: SessionDep,
) -> SubmissionResult:
    """Score a final deduction submission and trigger an ending."""
    return await submit_final_submission(session_id, payload, current_user, db)
