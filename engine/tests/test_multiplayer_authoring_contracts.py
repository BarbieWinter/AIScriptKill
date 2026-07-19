"""验证 standalone Multiplayer v1 创作契约及其 loader 隔离边界。"""

import json

import pytest
from pydantic import ValidationError

from engine.contracts.multiplayer_v1.authoring import (
    MULTIPLAYER_STAGE_ADAPTER,
    STAGE_SETTLEMENT_ADAPTER,
    FinalJudgmentSettlementDefinition,
    MultiplayerPolicy,
    NoSettlementDefinition,
    SecretVoteSettlementDefinition,
    SharedChoiceSettlementDefinition,
)
from engine.core.package_archive import PackageArchiveError
from engine.core.package_loader import load_package_archive
from engine.tests.package_loader_fixtures import minimal_package_files, package_archive


def _policy_json(**overrides: object) -> str:
    data: dict[str, object] = {
        "min_players": 2,
        "max_players": 6,
        "character_assignment": "required",
        "start_policy": "all_players_ready",
        "duplicate_characters": False,
    }
    data.update(overrides)
    return json.dumps(data)


def _settlements() -> list[dict[str, object]]:
    return [
        {"mode": "none"},
        {
            "mode": "secret_vote",
            "settlement_id": "vote-1",
            "question": "本阶段最可疑的人是谁？",
            "options": [
                {"id": "option-a", "text": "甲"},
                {"id": "option-b", "text": "乙"},
            ],
            "reveal": "named_ballots",
            "submission_change": "forbidden",
            "default_effect": "record_and_continue",
        },
        {
            "mode": "shared_choice",
            "settlement_id": "choice-1",
            "question": "是否继续调查？",
            "options": [{"id": "continue", "text": "继续调查"}],
            "reveal": "outcome_only",
            "submission_change": "allowed_before_complete",
            "default_effect": "record_and_continue",
        },
        {
            "mode": "final_judgment",
            "settlement_id": "judgment-1",
            "question": "最终判断是什么？",
            "answer_mode": "shared_choice",
            "options": [{"id": "suspect-a", "text": "指认甲"}],
            "reveal": "named_ballots",
            "submission_change": "forbidden",
            "default_effect": "branch",
        },
    ]


def _stage() -> dict[str, object]:
    return {
        "id": "stage-1",
        "chapters": {"character-a": "chapter-a-1", "character-b": "chapter-b-1"},
        "public_materials": [
            {"id": "scene-photo", "reveal_at": "stage_enter"},
            {"id": "witness-note", "reveal_at": "all_players_read"},
            {"id": "vote-summary", "reveal_at": "settlement_done"},
            {"id": "branch-letter", "reveal_at": "outcome:follow-shadow"},
        ],
        "discussion": {"suggested_minutes": 15, "close_policy": "all_players"},
        "settlement": _settlements()[1],
        "hints": [
            {
                "id": "motive-chain",
                "levels": ["回看时间线。", "比较两份证词。", "留意无法同时成立的陈述。"],
            }
        ],
    }


def test_multiplayer_policy_uses_public_yaml_names_and_strict_invariants() -> None:
    policy = MultiplayerPolicy.model_validate_json(_policy_json())

    assert policy.max_players == 6
    assert policy.character_assignment.value == "required"
    assert policy.duplicate_characters is False

    for invalid in (
        _policy_json(min_players=4, max_players=3),
        _policy_json(min_players="2"),
        _policy_json(duplicate_characters=True),
        _policy_json(future=True),
        json.dumps(
            {
                "min_players": 2,
                "max_players": 4,
                "character_assignment_policy": "required",
                "start_policy": "all_players_ready",
                "allow_duplicate_character_assignments": False,
            }
        ),
    ):
        with pytest.raises(ValidationError):
            MultiplayerPolicy.model_validate_json(invalid)


def test_all_settlement_modes_are_discriminated_and_round_trip() -> None:
    parsed = [
        STAGE_SETTLEMENT_ADAPTER.validate_json(json.dumps(definition))
        for definition in _settlements()
    ]
    round_tripped = [
        STAGE_SETTLEMENT_ADAPTER.validate_json(STAGE_SETTLEMENT_ADAPTER.dump_json(definition))
        for definition in parsed
    ]

    assert isinstance(round_tripped[0], NoSettlementDefinition)
    assert isinstance(round_tripped[1], SecretVoteSettlementDefinition)
    assert isinstance(round_tripped[2], SharedChoiceSettlementDefinition)
    assert isinstance(round_tripped[3], FinalJudgmentSettlementDefinition)
    assert round_tripped[1].reveal.value == "named_ballots"
    assert round_tripped[3].answer_mode.value == "shared_choice"
    assert STAGE_SETTLEMENT_ADAPTER.json_schema()["discriminator"]["propertyName"] == "mode"


def test_settlement_definitions_reject_invalid_local_shapes() -> None:
    duplicate_options = _settlements()[1]
    duplicate_options["options"] = [
        {"id": "same", "text": "甲"},
        {"id": "same", "text": "乙"},
    ]
    empty_options = _settlements()[2]
    empty_options["options"] = []
    missing_question = _settlements()[1]
    del missing_question["question"]
    old_field_name = _settlements()[1]
    old_field_name["submission_change_policy"] = old_field_name.pop("submission_change")
    final_without_answer_mode = _settlements()[3]
    del final_without_answer_mode["answer_mode"]

    invalid_definitions: list[dict[str, object]] = [
        duplicate_options,
        empty_options,
        missing_question,
        old_field_name,
        final_without_answer_mode,
        {"mode": "future_mode"},
        {"mode": "none", "options": []},
    ]
    for invalid in invalid_definitions:
        with pytest.raises(ValidationError):
            STAGE_SETTLEMENT_ADAPTER.validate_json(json.dumps(invalid))


def test_complete_multiplayer_stage_round_trips_and_validates_local_ids() -> None:
    stage = MULTIPLAYER_STAGE_ADAPTER.validate_json(json.dumps(_stage()))
    restored = MULTIPLAYER_STAGE_ADAPTER.validate_json(MULTIPLAYER_STAGE_ADAPTER.dump_json(stage))

    assert restored == stage
    assert [material.reveal_at for material in restored.public_materials] == [
        "stage_enter",
        "all_players_read",
        "settlement_done",
        "outcome:follow-shadow",
    ]
    assert restored.discussion.suggested_minutes == 15
    assert len(restored.hints[0].levels) == 3

    invalid_stages: list[dict[str, object]] = []
    for trigger in ("outcome:", "timer", ""):
        invalid = _stage()
        invalid["public_materials"] = [{"id": "material", "reveal_at": trigger}]
        invalid_stages.append(invalid)

    invalid = _stage()
    invalid["discussion"] = {"suggested_minutes": 0, "close_policy": "all_players"}
    invalid_stages.append(invalid)

    for levels in (["one", "two"], ["one", "two", "three", "four"], ["one", "", "three"]):
        invalid = _stage()
        invalid["hints"] = [{"id": "hint", "levels": levels}]
        invalid_stages.append(invalid)

    duplicate_material = _stage()
    duplicate_material["public_materials"] = [
        {"id": "same", "reveal_at": "stage_enter"},
        {"id": "same", "reveal_at": "settlement_done"},
    ]
    invalid_stages.append(duplicate_material)

    duplicate_hint = _stage()
    duplicate_hint["hints"] = [
        {"id": "same", "levels": ["1", "2", "3"]},
        {"id": "same", "levels": ["a", "b", "c"]},
    ]
    invalid_stages.append(duplicate_hint)

    for invalid_stage in invalid_stages:
        with pytest.raises(ValidationError):
            MULTIPLAYER_STAGE_ADAPTER.validate_json(json.dumps(invalid_stage))


def test_authoring_contracts_remain_standalone_from_legacy_package_loader() -> None:
    legacy_files = minimal_package_files()
    package = load_package_archive(package_archive(legacy_files))

    assert package.package.id == "minimal-case"
    assert "multiplayer" not in package.package.config

    multiplayer_files = minimal_package_files()
    multiplayer_files["package.yml"] += """
multiplayer:
  min_players: 2
  max_players: 4
  character_assignment: required
  start_policy: all_players_ready
  duplicate_characters: false
"""
    with pytest.raises(PackageArchiveError) as exc_info:
        load_package_archive(package_archive(multiplayer_files))

    assert exc_info.value.code == "INVALID_PACKAGE_SCHEMA"
    assert "multiplayer" in exc_info.value.message
