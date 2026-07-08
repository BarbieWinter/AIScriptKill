from dataclasses import dataclass
from typing import assert_never

from engine.api.schemas.common import JsonValue
from engine.core.condition_evaluator import evaluate_condition
from engine.core.game_state import GameState
from engine.core.package_schema import ClueRecord, EndingRecord, ScriptPackageImport, StageRecord
from engine.core.package_validation_context import json_mapping_list, metadata_texts


@dataclass(frozen=True, slots=True)
class PackageRuntimeIndex:
    package: ScriptPackageImport

    def stage_by_id(self, stage_id: str) -> StageRecord:
        for stage in self.package.stages:
            if stage.id == stage_id:
                return stage
        raise StageLookupError(stage_id)

    def clue_by_id(self, clue_id: str) -> ClueRecord:
        for clue in self.package.clues:
            if clue.id == clue_id:
                return clue
        raise ClueLookupError(clue_id)

    def next_stage_id(self, stage_id: str) -> str | None:
        next_index = self.stage_index(stage_id) + 1
        if next_index >= len(self.package.stages):
            return None
        return self.ordered_stages()[next_index].id

    def can_transition(self, state: GameState, target_stage: str) -> bool:
        current_stage = state["current_stage"]
        if target_stage == self.next_stage_id(current_stage):
            return True
        current_definition = self.stage_by_id(current_stage).definition
        if target_stage in metadata_texts(current_definition.get("allowed_transitions")):
            return True
        if boolean_config(current_definition.get("allow_stage_jump")):
            return True
        if self.stage_index(target_stage) < self.stage_index(current_stage):
            return boolean_config(current_definition.get("allow_stage_regression"))
        return False

    def stage_index(self, stage_id: str) -> int:
        for index, stage in enumerate(self.ordered_stages()):
            if stage.id == stage_id:
                return index
        return len(self.package.stages)

    def ordered_stages(self) -> tuple[StageRecord, ...]:
        return tuple(sorted(self.package.stages, key=lambda stage: stage.sort_order))

    def apply_stage_runtime(self, state: GameState, stage: StageRecord) -> None:
        state["available_actions"] = text_list(stage.definition.get("available_actions"))
        state["available_characters"] = text_list(stage.definition.get("available_characters"))
        state["available_scenes"] = text_list(stage.definition.get("available_scenes"))
        if state["current_scene"] == "" and len(state["available_scenes"]) > 0:
            state["current_scene"] = state["available_scenes"][0]

    def matching_ending(self, state: GameState) -> EndingRecord | None:
        for ending in self.package.endings:
            if evaluate_condition(ending.condition, state):
                return ending
        return None

    def stage_exit_condition_met(self, state: GameState) -> bool:
        stage = self.stage_by_id(state["current_stage"])
        for condition in json_mapping_list(stage.definition.get("exit_conditions")):
            if evaluate_condition(condition, state):
                return True
        return False


@dataclass(frozen=True, slots=True)
class StageLookupError(Exception):
    stage_id: str

    def __str__(self) -> str:
        return f"stage not found: {self.stage_id}"


@dataclass(frozen=True, slots=True)
class ClueLookupError(Exception):
    clue_id: str

    def __str__(self) -> str:
        return f"clue not found: {self.clue_id}"


def boolean_config(value: JsonValue | None) -> bool:
    match value:
        case bool() as flag:
            return flag
        case str() as text:
            return text.lower() == "true"
        case int() | float() | list() | dict() | None:
            return False
        case unreachable:
            assert_never(unreachable)


def record_dialog(state: GameState, character_id: str | None, text: str | None) -> None:
    if character_id is None:
        return
    state["character_dialog_counts"][character_id] = (
        state["character_dialog_counts"].get(character_id, 0) + 1
    )
    if text is not None:
        state["player_utterances"].append(text)


def record_evidence_presentation(state: GameState, target: str | None) -> None:
    if target is None or ":" not in target:
        return
    evidence_id, character_id = target.split(":", maxsplit=1)
    state["evidences_shown_to_npcs"].append(
        {"evidence_id": evidence_id, "character_id": character_id},
    )


def text_list(value: JsonValue | None) -> list[str]:
    if not isinstance(value, list):
        return []
    results: list[str] = []
    for item in value:
        match item:
            case str() as action:
                results.append(action)
            case dict() as action_definition:
                action_id = action_definition.get("id")
                if isinstance(action_id, str):
                    results.append(action_id)
            case int() | float() | bool() | list() | None:
                continue
    return results
