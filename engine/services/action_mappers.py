"""将 API 动作载荷映射为已校验的领域动作指令。"""

from engine.api.schemas import (
    ActionRequest,
    ActionResponse,
    AdvanceDenied,
    CardResult,
    EvidenceReaction,
    FinalSubmissionRequest,
    NpcResponse,
    SceneResult,
    StageTransition,
    SubmissionResult,
)
from engine.api.schemas.actions import StageTransitionState, SubmissionDetail
from engine.api.schemas.common import DiscoveredClue, EventTrigger, JsonValue, MediaTrigger
from engine.repositories.session_repository import (
    ChatMessageDraft,
    DiscoveryDraft,
    SessionActionEffect,
)

# ── 行动响应与持久化副作用 ──


def action_response_and_effect(
    payload: ActionRequest,
) -> tuple[ActionResponse, SessionActionEffect]:
    """将一个已校验动作映射为确定性响应和持久化效果。"""

    match payload.action:
        case "talk_to_npc":
            character_id = payload.character_id or "wangdada"
            reply_text = "我昨晚？我一直在厨房忙活啊，没出过门。"
            response = NpcResponse(
                type="npc_response",
                character_id=character_id,
                text=reply_text,
                emotion="normal",
                state_changes={"trust": -5, "nervous": 10},
                triggered_events=[],
                media_triggers=[],
            )
            return response, SessionActionEffect(
                state_patch={},
                chat_messages=(
                    ChatMessageDraft(role="player", text=payload.message or ""),
                    ChatMessageDraft(
                        role="npc",
                        character_id=character_id,
                        text=reply_text,
                        emotion="normal",
                    ),
                ),
            )
        case "examine_scene":
            clue = DiscoveredClue(clue_id="broken_glass", name="碎玻璃碴")
            response = SceneResult(
                type="scene_result",
                scene_id=payload.scene_id or "crime_scene",
                hotspot_id=payload.hotspot_id or "back_door",
                dm_narration="你推开后门，雪地上有杂乱的脚印……",
                discovered_clues=[clue],
                discovered_evidences=[],
                media_triggers=[MediaTrigger(action="play_audio", asset_id="sfx_discovery")],
            )
            return response, SessionActionEffect(
                state_patch={"unlocked_clues": [clue.clue_id], "current_scene": response.scene_id},
                discoveries=(DiscoveryDraft(entity_type="clue", entity_id=clue.clue_id),),
            )
        case "show_evidence":
            response = EvidenceReaction(
                type="evidence_reaction",
                character_id=payload.character_id or "wangdada",
                text="这刀是我家的！但昨晚它明明在厨房里……",
                emotion="shocked",
                state_changes={"shock": 20, "fear": 30, "trust": -15},
                triggered_dialog="knife_reaction",
                media_triggers=[MediaTrigger(action="play_audio", asset_id="sfx_tension")],
            )
            return response, SessionActionEffect(state_patch={})
        case "use_card":
            response = CardResult(
                type="card_result",
                card_id=payload.card_id or "interrogation_card",
                remaining_uses=1,
                effect="skill_interrogation",
                character_id=payload.target_character_id or "wangdada",
                text="（被你严厉质问，王大达明显动摇了）",
                effect_description="王大达的紧张+30，可疑度+20",
            )
            return response, SessionActionEffect(state_patch={})
        case "request_advance":
            response = StageTransition(
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
            available_actions_patch: list[JsonValue] = []
            available_actions_patch.extend(response.new_state.available_actions)
            return response, SessionActionEffect(
                state_patch={
                    "current_stage": response.to_stage,
                    "stage_name": "第一幕事件",
                    "available_actions": available_actions_patch,
                },
            )
        case "open_clue_board":
            response = AdvanceDenied(
                type="advance_denied",
                reason="线索板由前端本地视图打开，后端仅返回当前线索数据。",
                hint="调用 /sessions/{session_id}/clues 获取线索列表。",
                suggested_action="examine_scene",
                suggested_target="crime_scene",
            )
            return response, SessionActionEffect(state_patch={})


# ── 最终推理评分映射 ──


def final_submission_result(payload: FinalSubmissionRequest) -> SubmissionResult:
    """按照当前确定性最终提交契约评分。"""

    hit_count = len(payload.key_evidences)
    score = min(100, 55 + hit_count * 10)
    return SubmissionResult(
        type="submission_result",
        correct=True,
        score=score,
        detail=SubmissionDetail(
            correct_suspect=True,
            correct_motive=True,
            key_evidence_hit_rate=f"{hit_count}/5",
            missed_key_evidences=["hidden_letter", "phone_record"],
        ),
        ending_id="truth_revealed",
        triggered_events=[
            EventTrigger(action="play_audio", asset_id="ending_bgm_true"),
            EventTrigger(action="dm_narrate", text="真相，终于浮出水面……"),
        ],
    )


def submission_result_payload(result: SubmissionResult) -> dict[str, JsonValue]:
    """将提交结果序列化为可供存储的 JSON 兼容值。"""

    return result.model_dump(mode="json")
