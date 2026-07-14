from sqlalchemy.engine import RowMapping

from engine.api.schemas import (
    CardListResponse,
    CharacterChapterListResponse,
    CharacterChapterResponse,
    CharacterListResponse,
    ChatHistoryResponse,
    ClueListResponse,
    EvidenceListResponse,
    ReviewResponse,
)
from engine.api.schemas.queries import (
    Card,
    CharacterChapterSummary,
    CharacterSummary,
    ChatMessage,
    Clue,
    Evidence,
)
from engine.api.schemas.reviews import ReviewBreakdown
from engine.core.game_state import EvidencePresentation
from engine.repositories.session_repository import CharacterChapterAccess, StoredSession
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


def evidences_response(
    rows: list[RowMapping],
    evidences_shown_to_npcs: list[EvidencePresentation],
) -> EvidenceListResponse:
    return EvidenceListResponse(
        evidences=[
            Evidence(
                id=row["evidence_id"],
                name=row["name"],
                image_url=row["image_url"] or "",
                description=row["description_surface"],
                status=row["status"],
                can_show_to_npc=True,
                shown_to_characters=_shown_character_ids(
                    row["evidence_id"],
                    evidences_shown_to_npcs,
                ),
            )
            for row in rows
        ],
    )


def _shown_character_ids(
    evidence_id: str,
    presentations: list[EvidencePresentation],
) -> list[str]:
    result: list[str] = []
    for item in presentations:
        if item.get("evidence_id") != evidence_id:
            continue
        character_id = item.get("character_id")
        if character_id and character_id not in result:
            result.append(character_id)
    return result


def character_chapters_response(rows: list[RowMapping]) -> CharacterChapterListResponse:
    return CharacterChapterListResponse(
        chapters=[
            CharacterChapterSummary(
                id=row["chapter_id"],
                character_id=row["character_id"],
                order=row["sort_order"],
                title=row["title"],
                status=row["status"],
            )
            for row in rows
        ],
    )


def character_chapter_response(chapter: CharacterChapterAccess) -> CharacterChapterResponse:
    return CharacterChapterResponse(
        id=chapter.chapter_id,
        character_id=chapter.character_id,
        order=chapter.sort_order,
        title=chapter.title,
        status=chapter.status,
        content=chapter.content,
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
    breakdown = row["breakdown"]
    selected_option = breakdown.get("selected_option")
    correct_option = breakdown.get("correct_option")
    judgment_correct = selected_option == correct_option
    total_clues_found = len(session.state.unlocked_clues)
    total_clues_available = 1 if session.script_id == "snow-village" else 0
    return ReviewResponse(
        session_id=str(session.id),
        script_id=session.script_id,
        score=row["score"],
        max_score=row["max_score"],
        rating=row["rating"] or "N/A",
        duration_minutes=0,
        breakdown=ReviewBreakdown(
            suspect_correct=judgment_correct,
            motive_correct=judgment_correct,
            key_evidence_hit_rate="1/1" if judgment_correct else "0/1",
            wrong_accusations=0 if judgment_correct else 1,
            total_clues_found=total_clues_found,
            total_clues_available=total_clues_available,
            clue_coverage=(
                "100%"
                if total_clues_available and total_clues_found >= total_clues_available
                else "0%"
            ),
            hints_used=0,
        ),
        missed_key_clues=[],
        optimal_path=["clue-back-alley-note", "evidence-back-door-image"],
        player_path=[
            *session.state.unlocked_clues,
            *session.state.discovered_evidences,
        ],
        truth_summary=row["truth_summary"] or "",
    )
