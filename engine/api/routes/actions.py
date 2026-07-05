from fastapi import APIRouter

from engine.api.middleware.auth import CurrentUserDep
from engine.api.schemas import (
    ActionRequest,
    ActionResponse,
    FinalSubmissionRequest,
    SubmissionResult,
)
from engine.services.session_service import (
    perform_action_stub,
    submit_final_stub,
)

# ── 游戏操作路由 ──

router = APIRouter(prefix="/sessions/{session_id}", tags=["actions"])


# ── 行动执行 ──


@router.post("/actions", response_model=ActionResponse)
async def perform_action(
    session_id: str,
    payload: ActionRequest,
    _current_user: CurrentUserDep,
) -> ActionResponse:
    """Route a player action into the game engine action pipeline."""
    return perform_action_stub(session_id, payload)


# ── 最终推理提交 ──


@router.post("/final-submission", response_model=SubmissionResult)
async def submit_final(
    session_id: str,
    payload: FinalSubmissionRequest,
    _current_user: CurrentUserDep,
) -> SubmissionResult:
    """Score a final deduction submission and trigger an ending."""
    return submit_final_stub(session_id, payload)
