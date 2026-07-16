from collections.abc import Mapping
from pathlib import Path
from typing import cast

from engine.agents.npc_agent import DeterministicNpcResponder
from engine.api.schemas import ActionRequest, FinalSubmissionRequest
from engine.core.game_state import create_initial_state
from engine.core.package_loader import load_package_directory
from engine.core.script_engine import ScriptEngine
from engine.services.action_mappers import final_submission_result
from engine.services.runtime_action_mappers import runtime_action_result


def snow_village_package():
    return load_package_directory(Path(__file__).parents[2] / "script-packages" / "snow-village")


def test_snow_village_package_is_executable_content_authority() -> None:
    package = snow_village_package()

    assert package.package.id == "snow-village"
    assert [stage.id for stage in package.stages] == [
        "return_to_snow_village",
        "investigate_back_alley",
        "confront_wangdada",
        "back_door_judgement",
    ]
    assert [chapter.id for chapter in package.chapters] == [
        "zhuosiyuan-chapter-01",
        "zhuosiyuan-chapter-02",
    ]
    assert [clue.id for clue in package.clues] == ["clue-back-alley-note"]
    assert [evidence.id for evidence in package.evidences] == ["evidence-back-door-image"]
    assert package.warnings == ()


async def test_snow_village_graph_reaches_confrontation_through_real_actions() -> None:
    package = snow_village_package()
    engine = ScriptEngine.from_package(
        package,
        npc_responder=DeterministicNpcResponder("我只说自己知道的。"),
    )
    state = create_initial_state(
        session_id="session-snow-village",
        script_id=package.package.id,
        player_id="anonymous",
        player_character_id="zhuosiyuan",
        entry_stage="return_to_snow_village",
    )
    state["read_character_chapters"].append("zhuosiyuan-chapter-01")

    state = await engine.run_action(
        state,
        action_id="talk_to_npc",
        target="wangdada",
        text="今晚还有谁来过？",
    )
    state = await engine.run_action(
        state,
        action_id="request_advance",
        target="request_advance",
    )
    assert state["current_stage"] == "investigate_back_alley"

    before_examine = state
    state = await engine.run_action(
        state,
        action_id="examine_scene",
        target="back-alley:back-door-traces",
    )
    response, effect = runtime_action_result(
        ActionRequest(
            action="examine_scene",
            scene_id="back-alley",
            hotspot_id="back-door-traces",
        ),
        before_examine,
        state,
        package,
    )
    assert response.type == "scene_result"
    assert [item.clue_id for item in response.discovered_clues] == ["clue-back-alley-note"]
    assert response.discovered_evidences == ["evidence-back-door-image"]
    assert [(item.entity_type, item.entity_id) for item in effect.discoveries] == [
        ("clue", "clue-back-alley-note"),
        ("evidence", "evidence-back-door-image"),
    ]

    state["viewed_evidences"].append("evidence-back-door-image")
    state = await engine.run_action(
        state,
        action_id="request_advance",
        target="request_advance",
    )
    assert state["current_stage"] == "confront_wangdada"
    assert "zhuosiyuan-chapter-02" in state["unlocked_character_chapters"]

    state["read_character_chapters"].append("zhuosiyuan-chapter-02")
    state = await engine.run_action(
        state,
        action_id="show_evidence",
        target="evidence-back-door-image:wangdada",
    )
    state = await engine.run_action(
        state,
        action_id="request_advance",
        target="request_advance",
    )
    assert state["current_stage"] == "back_door_judgement"
    assert state["evidences_shown_to_npcs"] == [
        {
            "evidence_id": "evidence-back-door-image",
            "character_id": "wangdada",
        }
    ]


def test_snow_village_judgment_uses_package_answer_and_evidence_boundary() -> None:
    package = snow_village_package()
    judgment_stage = next(stage for stage in package.stages if stage.id == "back_door_judgement")
    special_rules = judgment_stage.definition.get("special_rules")
    assert isinstance(special_rules, Mapping)
    judgment = cast(Mapping[object, object], special_rules).get("judgement")
    assert isinstance(judgment, Mapping)
    correct_option = cast(Mapping[object, object], judgment).get("correct_option")
    assert isinstance(correct_option, str)

    correct = final_submission_result(
        FinalSubmissionRequest(option="C"),
        correct_option=correct_option,
    )
    unsupported = final_submission_result(
        FinalSubmissionRequest(option="A"),
        correct_option=correct_option,
    )

    assert correct.correct is True
    assert correct.score == 100
    assert correct.detail.selected_option == "C"
    assert correct.detail.correct_option == "C"
    assert correct.detail.npc_disclosure is None
    assert unsupported.correct is False
    assert unsupported.score == 0
    assert unsupported.detail.npc_disclosure is None
    assert unsupported.detail.evidence_boundary == "该选项未匹配当前阶段声明的正确判断。"
