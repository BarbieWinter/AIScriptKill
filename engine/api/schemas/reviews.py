"""定义会话最终复盘和分数明细模型。"""

from pydantic import Field

from engine.api.schemas.common import ApiModel

# ── 复盘评分明细 ──


class ReviewBreakdown(ApiModel):
    """将最终分数拆分为推理、线索和提示指标。"""

    suspect_correct: bool = Field(description="Whether suspect was correct.")
    motive_correct: bool = Field(description="Whether motive was correct.")
    key_evidence_hit_rate: str = Field(description="Evidence hit rate.")
    wrong_accusations: int = Field(description="Wrong accusation count.")
    total_clues_found: int = Field(description="Found clue count.")
    total_clues_available: int = Field(description="Available clue count.")
    clue_coverage: str = Field(description="Coverage percentage string.")
    hints_used: int = Field(description="Hint usage count.")


class MissedKeyClue(ApiModel):
    """描述玩家流程中遗漏的一条关键线索。"""

    id: str = Field(description="Clue ID.")
    name: str = Field(description="Clue display name.")
    description: str = Field(description="Clue description.")


# ── 复盘结果响应 ──


class ReviewResponse(ApiModel):
    """返回已完成会话的分数、路径和真相摘要。"""

    session_id: str = Field(description="Game session ID.")
    script_id: str = Field(description="Script package ID.")
    score: int = Field(description="Player score.")
    max_score: int = Field(description="Maximum score.")
    rating: str = Field(description="Rating label.")
    duration_minutes: int = Field(description="Play duration.")
    breakdown: ReviewBreakdown = Field(description="Score breakdown.")
    missed_key_clues: list[MissedKeyClue] = Field(description="Missed key clues.")
    optimal_path: list[str] = Field(description="Optimal evidence/clue path.")
    player_path: list[str] = Field(description="Player evidence/clue path.")
    truth_summary: str = Field(description="Truth summary.")
