import json
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import cast
from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

import engine.services.session_service as session_service
from engine.api.errors import ApiError
from engine.api.middleware.auth import CurrentUser
from engine.api.schemas import FinalSubmissionRequest
from engine.core.package_loader import load_package_directory
from engine.core.package_schema import ScriptPackageImport
from engine.repositories.session_models import SessionRuntimeState, StoredSession
from engine.services.action_mappers import final_submission_result
from engine.services.session_response_mappers import (
    judgement_definition,
    presentation_response,
)


def _snow_package() -> ScriptPackageImport:
    return load_package_directory(Path(__file__).parents[2] / "script-packages" / "snow-village")


def _session(*, stage_id: str, scene_id: str, script_id: str = "snow-village") -> StoredSession:
    timestamp = datetime(2026, 7, 16, tzinfo=UTC)
    return StoredSession(
        id=UUID("00000000-0000-0000-0000-000000000009"),
        script_id=script_id,
        player_id=None,
        player_character_id="zhuosiyuan",
        state=SessionRuntimeState(
            current_stage=stage_id,
            stage_name="当前阶段",
            available_actions=["open_clue_board"],
            available_characters=["wangdada"],
            current_scene=scene_id,
        ),
        status="in_progress",
        created_at=timestamp,
        updated_at=timestamp,
    )


def test_presentation_projects_only_spoiler_safe_current_package_fields() -> None:
    package = _snow_package()
    stage = next(item for item in package.stages if item.id == "back_door_judgement")
    scene = next(item for item in package.scenes if item.id == "restaurant-hall")

    response = presentation_response(
        _session(stage_id=stage.id, scene_id=scene.id),
        stage,
        scene,
    )
    payload = response.model_dump(mode="json", exclude_none=True)

    assert payload == {
        "stage": {
            "id": "back_door_judgement",
            "name": "后门判断",
            "available_actions": ["open_clue_board"],
            "available_characters": ["wangdada"],
        },
        "scene": {
            "id": "restaurant-hall",
            "name": "王氏杀猪菜前厅",
            "description": "已经打烊的饭馆前厅，炉火尚未完全熄灭。",
            "ambient_color": "#3b2a22",
            "hotspots": [],
        },
        "judgement": {
            "question": "根据当前材料，哪项最符合已证实事实？",
            "options": [
                {"id": "A", "text": "陈吉在21:13从后门进入，目的是偷走旧账本。"},
                {"id": "B", "text": "王大达伪造便签，试图掩盖自己与旧案的关系。"},
                {
                    "id": "C",
                    "text": (
                        "王大达关于没人来过的说法不完整；至少可确认后门在21:13半开，"
                        "但不能确认开门者和目的。"
                    ),
                },
                {"id": "D", "text": "后门异常证明饭馆当晚发生过犯罪。"},
            ],
        },
    }
    serialized = json.dumps(payload, ensure_ascii=False)
    for forbidden in (
        "correct_option",
        "on_click",
        "effects",
        "narration",
        "conditions",
        "storage://",
        "dm_narrate",
        "private",
    ):
        assert forbidden not in serialized


def test_presentation_whitelists_hotspot_geometry_and_suppresses_local_asset_locator() -> None:
    package = _snow_package()
    stage = next(item for item in package.stages if item.id == "investigate_back_alley")
    scene = next(item for item in package.scenes if item.id == "back-alley")

    payload = presentation_response(
        _session(stage_id=stage.id, scene_id=scene.id),
        stage,
        scene,
    ).model_dump(mode="json", exclude_none=True)

    assert payload["scene"]["hotspots"] == [
        {
            "id": "back-door-traces",
            "label": "后门旁的痕迹",
            "x": 58.0,
            "y": 44.0,
        }
    ]
    assert "background_url" not in payload["scene"]
    serialized = json.dumps(payload, ensure_ascii=False)
    assert "on_click" not in serialized
    assert "clue_discover" not in serialized
    assert "evidence_discover" not in serialized


def test_judgement_accepts_ordered_generic_option_ids_and_rejects_invalid_answer_id() -> None:
    definition = {
        "special_rules": {
            "judgement": {
                "title": "Choose",
                "question": "Which is supported?",
                "correct_option": "supported",
                "options": [
                    {"id": "unsupported", "text": "Unsupported"},
                    {"id": "supported", "text": "Supported"},
                ],
            }
        }
    }

    judgement = judgement_definition(definition)

    assert judgement is not None
    assert judgement.options == (
        ("unsupported", "Unsupported"),
        ("supported", "Supported"),
    )
    assert judgement.option_ids == frozenset(("unsupported", "supported"))
    assert (
        judgement_definition(
            {
                "special_rules": {
                    "judgement": {
                        "question": "Broken",
                        "correct_option": "missing",
                        "options": {"declared": "Declared"},
                    }
                }
            }
        )
        is None
    )


def test_final_submission_result_is_not_restricted_to_c_or_letter_ids() -> None:
    result = final_submission_result(
        FinalSubmissionRequest(option="supported"),
        correct_option="supported",
    )

    assert result.correct is True
    assert result.detail.selected_option == "supported"
    assert result.detail.correct_option == "supported"


class _SubmissionRepository:
    def __init__(self, stored_session: StoredSession) -> None:
        self.stored_session = stored_session
        self.saved = False

    async def get_session(self, _session_id: UUID) -> StoredSession:
        return self.stored_session

    async def save_final_submission(self, *_args: object) -> StoredSession:
        self.saved = True
        return self.stored_session


async def test_submit_final_validates_option_against_current_stage_yaml(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _snow_package()
    source_stage = next(item for item in source.stages if item.id == "back_door_judgement")
    stage = replace(
        source_stage,
        id="generic_decision",
        definition={
            "special_rules": {
                "judgement": {
                    "question": "Choose",
                    "correct_option": "yes",
                    "options": {"no": "No", "yes": "Yes"},
                }
            }
        },
    )
    package = replace(
        source,
        package=replace(source.package, id="generic-package"),
        stages=(stage,),
    )
    stored_session = _session(
        script_id="generic-package",
        stage_id="generic_decision",
        scene_id="restaurant-hall",
    )
    repository = _SubmissionRepository(stored_session)
    monkeypatch.setattr(session_service, "SessionRepository", lambda _db: repository)

    async def fake_runtime_package(
        _db: AsyncSession,
        _script_id: str,
    ) -> ScriptPackageImport:
        return package

    monkeypatch.setattr(session_service, "get_runtime_package", fake_runtime_package)
    db = cast(AsyncSession, cast(object, object()))
    user = CurrentUser(subject="anonymous", role="anonymous", app_role=None)

    with pytest.raises(ApiError) as invalid_error:
        await session_service.submit_final(
            str(stored_session.id),
            FinalSubmissionRequest(option="undeclared"),
            user,
            db,
        )
    assert invalid_error.value.error.code == "INVALID_JUDGMENT_OPTION"
    assert repository.saved is False

    result = await session_service.submit_final(
        str(stored_session.id),
        FinalSubmissionRequest(option="yes"),
        user,
        db,
    )
    assert result.correct is True
    assert result.detail.correct_option == "yes"
    assert repository.saved is True
