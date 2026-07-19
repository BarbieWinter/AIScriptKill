from collections.abc import Mapping
from dataclasses import dataclass
from typing import cast
from urllib.parse import urlsplit

from engine.api.schemas import (
    CreateSessionResponse,
    SessionPresentationResponse,
    SessionStateResponse,
    UpdateSessionResponse,
)
from engine.api.schemas.common import PendingMedia
from engine.api.schemas.sessions import (
    SessionPresentationHotspot,
    SessionPresentationJudgement,
    SessionPresentationJudgementOption,
    SessionPresentationScene,
    SessionPresentationStage,
)
from engine.core.package_schema import SceneRecord, StageRecord
from engine.repositories.session_repository import StoredSession
from engine.services.mapper_utils import timestamp

# ── 会话响应映射 ──


def _legacy_character_id(session: StoredSession) -> str:
    if session.mode != "legacy_single" or session.player_character_id is None:
        raise ValueError("legacy response requires a player character")
    return session.player_character_id


def create_response(session: StoredSession) -> CreateSessionResponse:
    character_id = _legacy_character_id(session)
    return CreateSessionResponse(
        session_id=str(session.id),
        script_id=session.script_id,
        status=session.status,
        current_stage=session.state.current_stage,
        player_character_id=character_id,
        available_actions=session.state.available_actions,
        created_at=timestamp(session.created_at),
    )


# ── 当前状态响应 ──


def state_response(session: StoredSession, stage_name: str | None) -> SessionStateResponse:
    state = session.state
    character_id = _legacy_character_id(session)
    return SessionStateResponse(
        session_id=str(session.id),
        script_id=session.script_id,
        status=session.status,
        current_stage=state.current_stage,
        stage_name=stage_name or state.stage_name,
        player_character_id=character_id,
        available_actions=state.available_actions,
        available_characters=state.available_characters,
        unlocked_clues_count=len(state.unlocked_clues),
        total_clues_in_round=max(len(state.unlocked_clues), 0),
        discovered_evidences=state.discovered_evidences,
        viewed_evidences=state.viewed_evidences,
        current_scene=state.current_scene,
        pending_media=[
            PendingMedia(id=item["id"], type=item["type"], status=item["status"])
            for item in state.pending_media
        ],
        revision=session.revision,
        event_head_sequence=session.event_head_sequence,
    )


# ── 当前展示投影 ──


@dataclass(frozen=True, slots=True)
class RuntimeJudgement:
    """保存服务端评分所需、但不会整体序列化到展示响应的判断定义。"""

    title: str | None
    question: str
    options: tuple[tuple[str, str], ...]
    correct_option: str

    @property
    def option_ids(self) -> frozenset[str]:
        return frozenset(option_id for option_id, _text in self.options)


def presentation_response(
    session: StoredSession,
    stage: StageRecord,
    scene: SceneRecord,
) -> SessionPresentationResponse:
    """从运行时包记录白名单投影当前阶段、场景和可选判断。"""

    judgement = judgement_definition(stage.definition)
    return SessionPresentationResponse(
        stage=SessionPresentationStage(
            id=stage.id,
            name=stage.name,
            available_actions=session.state.available_actions,
            available_characters=session.state.available_characters,
        ),
        scene=SessionPresentationScene(
            id=scene.id,
            name=scene.name,
            description=_optional_text(scene.definition.get("description")),
            ambient_color=_scene_ambient_color(scene.definition),
            background_url=_browser_safe_url(scene.background_url),
            hotspots=_public_hotspots(scene.definition.get("hotspots")),
        ),
        judgement=(
            SessionPresentationJudgement(
                title=judgement.title,
                question=judgement.question,
                options=[
                    SessionPresentationJudgementOption(id=option_id, text=text)
                    for option_id, text in judgement.options
                ],
            )
            if judgement is not None
            else None
        ),
    )


def judgement_definition(definition: Mapping[str, object]) -> RuntimeJudgement | None:
    """读取并完整校验当前阶段的有序判断选项和正确选项 ID。"""

    special_rules = definition.get("special_rules")
    if not isinstance(special_rules, Mapping):
        return None
    rules = cast(Mapping[object, object], special_rules)
    raw_judgement = rules.get("judgement")
    if not isinstance(raw_judgement, Mapping):
        return None
    judgement = cast(Mapping[object, object], raw_judgement)
    question = _required_text(judgement.get("question"))
    correct_option = _required_text(judgement.get("correct_option"))
    options = _judgement_options(judgement.get("options"))
    if question is None or correct_option is None or options is None:
        return None
    option_ids = {option_id for option_id, _text in options}
    if correct_option not in option_ids:
        return None
    return RuntimeJudgement(
        title=_optional_text(judgement.get("title")),
        question=question,
        options=options,
        correct_option=correct_option,
    )


def _judgement_options(value: object) -> tuple[tuple[str, str], ...] | None:
    if isinstance(value, Mapping):
        options: list[tuple[str, str]] = []
        for raw_id, raw_text in cast(Mapping[object, object], value).items():
            option_id = _required_text(raw_id)
            text = _required_text(raw_text)
            if option_id is None or text is None:
                return None
            options.append((option_id, text))
        return _unique_nonempty_options(options)
    if isinstance(value, list):
        options = []
        for raw_option in cast(list[object], value):
            if not isinstance(raw_option, Mapping):
                return None
            option = cast(Mapping[object, object], raw_option)
            option_id = _required_text(option.get("id"))
            text = _required_text(option.get("text"))
            if option_id is None or text is None:
                return None
            options.append((option_id, text))
        return _unique_nonempty_options(options)
    return None


def _unique_nonempty_options(
    options: list[tuple[str, str]],
) -> tuple[tuple[str, str], ...] | None:
    if len(options) == 0:
        return None
    option_ids = [option_id for option_id, _text in options]
    if len(option_ids) != len(set(option_ids)):
        return None
    return tuple(options)


def _public_hotspots(value: object) -> list[SessionPresentationHotspot]:
    if not isinstance(value, list):
        return []
    hotspots: list[SessionPresentationHotspot] = []
    for raw_hotspot in cast(list[object], value):
        if not isinstance(raw_hotspot, Mapping):
            continue
        hotspot = cast(Mapping[object, object], raw_hotspot)
        if _private_hotspot(hotspot):
            continue
        hotspot_id = _required_text(hotspot.get("id"))
        x = _number(hotspot.get("x"))
        y = _number(hotspot.get("y"))
        if hotspot_id is None or x is None or y is None:
            continue
        hotspots.append(
            SessionPresentationHotspot(
                id=hotspot_id,
                label=_optional_text(hotspot.get("label")) or hotspot_id,
                x=x,
                y=y,
                width=_number(hotspot.get("width")),
                height=_number(hotspot.get("height")),
            )
        )
    return hotspots


def _private_hotspot(hotspot: Mapping[object, object]) -> bool:
    visibility = hotspot.get("visibility")
    return (
        visibility in ("private", "dm_only")
        or hotspot.get("private") is True
        or hotspot.get("public") is False
    )


def _scene_ambient_color(definition: Mapping[str, object]) -> str | None:
    visual = definition.get("visual")
    if not isinstance(visual, Mapping):
        return None
    return _optional_text(cast(Mapping[object, object], visual).get("ambient_color"))


def _browser_safe_url(value: str | None) -> str | None:
    if value is None:
        return None
    if value.startswith("/") and not value.startswith("//"):
        return value
    parsed = urlsplit(value)
    if parsed.scheme in ("http", "https") and parsed.netloc:
        return value
    return None


def _number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value)


def _required_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    if len(text) == 0 or len(text) > 8_000:
        return None
    return text


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    return _required_text(value)


# ── 检查点恢复响应 ──


def restore_response(session: StoredSession, checkpoint_id: str) -> UpdateSessionResponse:
    return UpdateSessionResponse(
        session_id=str(session.id),
        status="restored",
        current_stage=session.state.current_stage,
        restored_from=checkpoint_id,
    )
