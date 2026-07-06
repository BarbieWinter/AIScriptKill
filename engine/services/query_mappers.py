from sqlalchemy.engine import RowMapping

from engine.api.schemas import (
    CardListResponse,
    CharacterListResponse,
    ChatHistoryResponse,
    ClueListResponse,
    EvidenceListResponse,
    ReviewResponse,
)
from engine.api.schemas.queries import Card, CharacterSummary, ChatMessage, Clue, Evidence
from engine.api.schemas.reviews import MissedKeyClue, ReviewBreakdown
from engine.repositories.session_repository import StoredSession
from engine.services.mapper_utils import definition_value, timestamp

# ── 资料列表响应映射 ──


def clues_response(rows: list[RowMapping]) -> ClueListResponse:
    return ClueListResponse(
        clues=[
            Clue(
                id=row["clue_id"],
                name=row["name"],
                image_url=row["image_url"] or "",
                description=row["description"],
                is_key=row["is_key"],
                importance=row["importance"],
                discovered_at=timestamp(row["discovered_at"]),
                status=row["status"],
            )
            for row in rows
        ],
    )


def evidences_response(rows: list[RowMapping]) -> EvidenceListResponse:
    return EvidenceListResponse(
        evidences=[
            Evidence(
                id=row["evidence_id"],
                name=row["name"],
                image_url=row["image_url"] or "",
                description=row["description_surface"],
                status=row["status"],
                can_show_to_npc=True,
                shown_to_characters=[],
            )
            for row in rows
        ],
    )


def characters_response(rows: list[RowMapping], fallback_ids: list[str]) -> CharacterListResponse:
    if rows:
        return CharacterListResponse(
            characters=[
                CharacterSummary(
                    id=row["character_id"],
                    name=row["name"],
                    portrait_url=definition_value(row, "portrait_url"),
                    current_mood="normal",
                    mood_description="状态正常",
                    dialogue_available=True,
                )
                for row in rows
            ],
        )
    return CharacterListResponse(
        characters=[
            CharacterSummary(
                id=character_id,
                name=character_id,
                portrait_url="",
                current_mood="normal",
                mood_description="状态正常",
                dialogue_available=True,
            )
            for character_id in fallback_ids
        ],
    )


def chat_history_response(rows: list[RowMapping]) -> ChatHistoryResponse:
    return ChatHistoryResponse(
        messages=[
            ChatMessage(
                id=str(row["id"]),
                role=row["role"],
                character_id=row["character_id"],
                text=row["text"],
                timestamp=timestamp(row["created_at"]),
                emotion=row["emotion"],
            )
            for row in rows
        ],
        next_page_token=None,
    )


def cards_response(rows: list[RowMapping]) -> CardListResponse:
    return CardListResponse(
        cards=[
            Card(
                id=row["evidence_id"],
                name=row["name"],
                type=row["type"],
                image_url=row["image_url"] or "",
                description=row["description_surface"],
                max_uses=1,
                remaining_uses=1,
                available=True,
            )
            for row in rows
        ],
    )


# ── 复盘缺省响应 ──


def review_response(session: StoredSession, row: RowMapping | None) -> ReviewResponse:
    if row is None:
        return ReviewResponse(
            session_id=str(session.id),
            script_id=session.script_id,
            score=0,
            max_score=100,
            rating="N/A",
            duration_minutes=0,
            breakdown=ReviewBreakdown(
                suspect_correct=False,
                motive_correct=False,
                key_evidence_hit_rate="0/5",
                wrong_accusations=0,
                total_clues_found=len(session.state.unlocked_clues),
                total_clues_available=0,
                clue_coverage="0%",
                hints_used=0,
            ),
            missed_key_clues=[],
            optimal_path=[],
            player_path=session.state.unlocked_clues,
            truth_summary="尚未完成最终推理。",
        )

    # ── 已完成复盘响应 ──
    return ReviewResponse(
        session_id=str(session.id),
        script_id=session.script_id,
        score=row["score"],
        max_score=row["max_score"],
        rating=row["rating"] or "N/A",
        duration_minutes=0,
        breakdown=ReviewBreakdown(
            suspect_correct=True,
            motive_correct=True,
            key_evidence_hit_rate=str(row["breakdown"].get("key_evidence_hit_rate", "0/5")),
            wrong_accusations=0,
            total_clues_found=len(session.state.unlocked_clues),
            total_clues_available=0,
            clue_coverage="0%",
            hints_used=0,
        ),
        missed_key_clues=[
            MissedKeyClue(id="hidden_letter", name="藏起的信", description="待剧本导入补全。"),
        ],
        optimal_path=[],
        player_path=session.state.unlocked_clues,
        truth_summary=row["truth_summary"] or "",
    )
