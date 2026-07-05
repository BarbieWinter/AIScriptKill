from typing import assert_never

from engine.api.schemas import (
    ActionRequest,
    ActionResponse,
    AdvanceDenied,
    CardListResponse,
    CardResult,
    CharacterListResponse,
    ChatHistoryResponse,
    ClueListResponse,
    CreateSessionRequest,
    CreateSessionResponse,
    EvidenceListResponse,
    EvidenceReaction,
    FinalSubmissionRequest,
    NpcResponse,
    ReviewResponse,
    SceneResult,
    SessionStateResponse,
    StageTransition,
    SubmissionResult,
    UpdateSessionRequest,
    UpdateSessionResponse,
)
from engine.api.schemas.actions import StageTransitionState, SubmissionDetail
from engine.api.schemas.common import DiscoveredClue, EventTrigger, MediaTrigger, PendingMedia
from engine.api.schemas.queries import (
    Card,
    CharacterSummary,
    ChatMessage,
    Clue,
    Evidence,
)
from engine.api.schemas.reviews import MissedKeyClue, ReviewBreakdown

# ── 临时桩数据常量 ──

TIMESTAMP = "2026-07-05T12:00:00Z"


# ── 会话生命周期桩 ──


def start_session_stub(payload: CreateSessionRequest) -> CreateSessionResponse:
    return CreateSessionResponse(
        session_id="abc-123",
        script_id=payload.script_id,
        status="in_progress",
        current_stage="prologue",
        player_character_id=payload.preferred_character_id,
        available_actions=["talk_to_npc", "examine_scene", "open_clue_board"],
        created_at=TIMESTAMP,
    )


def get_session_stub(session_id: str) -> SessionStateResponse:
    return SessionStateResponse(
        session_id=session_id,
        script_id="snow-village",
        status="in_progress",
        current_stage="act1_investigation",
        stage_name="第一幕·第一轮搜证",
        player_character_id="zhuosiyuan",
        available_actions=[
            "talk_to_npc",
            "examine_scene",
            "show_evidence",
            "use_card",
            "open_clue_board",
            "request_advance",
        ],
        available_characters=["zhuosiyuan", "cuikaiqiang", "wangdada"],
        unlocked_clues_count=2,
        total_clues_in_round=5,
        discovered_evidences=["broken_glass"],
        current_scene="crime_scene",
        pending_media=[
            PendingMedia(id="bgm_investigation", type="bgm", status="playing"),
        ],
    )


def restore_session_stub(
    session_id: str,
    payload: UpdateSessionRequest,
) -> UpdateSessionResponse:
    return UpdateSessionResponse(
        session_id=session_id,
        status="restored",
        current_stage="act1_investigation",
        restored_from=payload.checkpoint_id,
    )


# ── 游戏行动桩 ──


def perform_action_stub(_session_id: str, payload: ActionRequest) -> ActionResponse:
    match payload.action:
        case "talk_to_npc":
            return NpcResponse(
                type="npc_response",
                character_id=payload.character_id or "wangdada",
                text="我昨晚？我一直在厨房忙活啊，没出过门。",
                emotion="normal",
                state_changes={"trust": -5, "nervous": 10},
                triggered_events=[],
                media_triggers=[],
            )
        case "examine_scene":
            return SceneResult(
                type="scene_result",
                scene_id=payload.scene_id or "crime_scene",
                hotspot_id=payload.hotspot_id or "back_door",
                dm_narration="你推开后门，雪地上有杂乱的脚印……",
                discovered_clues=[
                    DiscoveredClue(clue_id="broken_glass", name="碎玻璃碴"),
                ],
                discovered_evidences=[],
                media_triggers=[
                    MediaTrigger(action="play_audio", asset_id="sfx_discovery"),
                ],
            )
        case "show_evidence":
            return EvidenceReaction(
                type="evidence_reaction",
                character_id=payload.character_id or "wangdada",
                text="这刀是我家的！但昨晚它明明在厨房里……",
                emotion="shocked",
                state_changes={"shock": 20, "fear": 30, "trust": -15},
                triggered_dialog="knife_reaction",
                media_triggers=[
                    MediaTrigger(action="play_audio", asset_id="sfx_tension"),
                ],
            )
        case "use_card":
            return CardResult(
                type="card_result",
                card_id=payload.card_id or "interrogation_card",
                remaining_uses=1,
                effect="skill_interrogation",
                character_id=payload.target_character_id or "wangdada",
                text="（被你严厉质问，王大达明显动摇了）",
                effect_description="王大达的紧张+30，可疑度+20",
            )
        case "request_advance":
            return StageTransition(
                type="stage_transition",
                from_stage="act1_investigation",
                to_stage="act1_event",
                transition_events=[
                    EventTrigger(action="play_audio", asset_id="broadcast_1"),
                    EventTrigger(action="dm_narrate", text="突然，村口的广播响了起来……"),
                ],
                new_state=StageTransitionState(
                    current_stage="act1_event",
                    available_actions=["talk_to_npc", "examine_scene", "show_evidence"],
                ),
            )
        case "open_clue_board":
            return AdvanceDenied(
                type="advance_denied",
                reason="线索板由前端本地视图打开，后端仅返回当前线索数据。",
                hint="调用 /sessions/{session_id}/clues 获取线索列表。",
                suggested_action="examine_scene",
                suggested_target="crime_scene",
            )

    assert_never(payload.action)


# ── 最终推理评分桩 ──


def submit_final_stub(
    _session_id: str,
    _payload: FinalSubmissionRequest,
) -> SubmissionResult:
    return SubmissionResult(
        type="submission_result",
        correct=True,
        score=85,
        detail=SubmissionDetail(
            correct_suspect=True,
            correct_motive=True,
            key_evidence_hit_rate="3/5",
            missed_key_evidences=["hidden_letter", "phone_record"],
        ),
        ending_id="truth_revealed",
        triggered_events=[
            EventTrigger(action="play_audio", asset_id="ending_bgm_true"),
            EventTrigger(action="dm_narrate", text="真相，终于浮出水面……"),
        ],
    )


# ── 会话数据查询桩 ──


def get_clues_stub(_session_id: str) -> ClueListResponse:
    return ClueListResponse(
        clues=[
            Clue(
                id="bloody_footprint",
                name="带血脚印",
                image_url="/storage/clues/1.jpg",
                description="雪地上有一串带血的脚印……",
                is_key=True,
                importance=4,
                discovered_at="2026-07-05T12:10:00Z",
                status="discovered",
            ),
        ],
    )


def get_evidences_stub(_session_id: str) -> EvidenceListResponse:
    return EvidenceListResponse(
        evidences=[
            Evidence(
                id="broken_glass",
                name="碎玻璃碴",
                image_url="/storage/evidences/broken_glass.jpg",
                description="玻璃边缘残留少量血迹。",
                status="discovered",
                can_show_to_npc=True,
                shown_to_characters=[],
            ),
        ],
    )


def get_characters_stub(_session_id: str) -> CharacterListResponse:
    return CharacterListResponse(
        characters=[
            CharacterSummary(
                id="wangdada",
                name="王大达",
                portrait_url="/storage/characters/wangdada.jpg",
                current_mood="nervous",
                mood_description="明显紧张，但仍试图保持镇定。",
                dialogue_available=True,
            ),
        ],
    )


def get_chat_history_stub(_session_id: str) -> ChatHistoryResponse:
    return ChatHistoryResponse(
        messages=[
            ChatMessage(
                id="msg-1",
                role="npc",
                character_id="wangdada",
                text="我一直在厨房忙活啊，没出过门。",
                timestamp="2026-07-05T12:12:00Z",
                emotion="normal",
            ),
        ],
        next_page_token=None,
    )


def get_cards_stub(_session_id: str) -> CardListResponse:
    return CardListResponse(
        cards=[
            Card(
                id="interrogation_card",
                name="严厉盘问",
                type="skill",
                image_url="/storage/cards/interrogation_card.jpg",
                description="对一名角色施压，提升其紧张度并解锁额外反应。",
                max_uses=2,
                remaining_uses=1,
                available=True,
            ),
        ],
    )


# ── 结算复盘桩 ──


def get_review_stub(session_id: str) -> ReviewResponse:
    return ReviewResponse(
        session_id=session_id,
        script_id="snow-village",
        score=85,
        max_score=100,
        rating="A",
        duration_minutes=96,
        breakdown=ReviewBreakdown(
            suspect_correct=True,
            motive_correct=True,
            key_evidence_hit_rate="3/5",
            wrong_accusations=0,
            total_clues_found=12,
            total_clues_available=15,
            clue_coverage="80%",
            hints_used=1,
        ),
        missed_key_clues=[
            MissedKeyClue(
                id="hidden_letter",
                name="藏起的信",
                description="柜底夹层里藏着一封旧信。",
            ),
        ],
        optimal_path=["bloody_footprint", "broken_glass", "hidden_letter"],
        player_path=["bloody_footprint", "broken_glass"],
        truth_summary="程俊借旧案复仇，利用雪夜制造不在场证明。",
    )
