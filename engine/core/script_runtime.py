"""提供状态机节点使用的运行时剧本包目录。"""

from dataclasses import dataclass

from engine.api.schemas.common import JsonValue
from engine.core.condition_evaluator import evaluate_condition
from engine.core.game_state import GameState
from engine.core.package_schema import (
    CharacterChapterRecord,
    ClueRecord,
    EndingRecord,
    ScriptPackageImport,
    StageRecord,
)
from engine.core.package_stage_index import stage_index_from_mapping
from engine.core.package_validation_context import json_mapping_list, metadata_texts


@dataclass(frozen=True, slots=True)
class PackageRuntimeIndex:
    """针对单个剧本包提供已校验的查询和跳转操作。"""

    package: ScriptPackageImport

    def stage_by_id(self, stage_id: str) -> StageRecord:
        """按 ID 返回阶段，否则抛出 StageLookupError。"""

        for stage in self.package.stages:
            if stage.id == stage_id:
                return stage
        raise StageLookupError(stage_id)

    def chapter_by_id(self, chapter_id: str) -> CharacterChapterRecord:
        """按 ID 返回人物章节，否则抛出 CharacterChapterLookupError。"""

        for chapter in self.package.chapters:
            if chapter.id == chapter_id:
                return chapter
        raise CharacterChapterLookupError(chapter_id)

    def clue_by_id(self, clue_id: str) -> ClueRecord:
        """按 ID 返回线索，否则抛出 ClueLookupError。"""

        for clue in self.package.clues:
            if clue.id == clue_id:
                return clue
        raise ClueLookupError(clue_id)

    def scene_hotspot_actions(
        self,
        scene_id: str,
        hotspot_id: str,
    ) -> list[dict[str, JsonValue]] | None:
        """返回场景热点动作；场景存在但热点缺失时返回 None。"""

        scene = next((item for item in self.package.scenes if item.id == scene_id), None)
        if scene is None:
            return None
        for hotspot in json_mapping_list(scene.definition.get("hotspots")):
            if hotspot.get("id") == hotspot_id:
                return json_mapping_list(hotspot.get("on_click"))
        return None

    def next_stage_id(self, stage_id: str) -> str | None:
        """返回下一个权威阶段，剧本包结束时返回 None。"""

        next_index = self.stage_index(stage_id) + 1
        if next_index >= len(self.package.stages):
            return None
        return self.ordered_stages()[next_index].id

    def can_transition(self, state: GameState, target_stage: str) -> bool:
        """强制执行相邻、显式、跳跃和回退跳转规则。"""

        current_stage = state["current_stage"]
        current_index = self.stage_index(current_stage)
        target_index = self.stage_index(target_stage)
        current_definition = self.stage_by_id(current_stage).definition
        explicit_targets = metadata_texts(current_definition.get("allowed_transitions"))
        if target_index < current_index:
            return target_stage in explicit_targets or boolean_config(
                current_definition.get("allow_stage_regression")
            )
        if target_stage == self.next_stage_id(current_stage):
            return True
        if target_stage in explicit_targets:
            return True
        return boolean_config(current_definition.get("allow_stage_jump"))

    def stage_index(self, stage_id: str) -> int:
        """返回阶段的权威位置，缺失时返回末尾哨兵值。"""

        for index, stage in enumerate(self.ordered_stages()):
            if stage.id == stage_id:
                return index
        return len(self.package.stages)

    def ordered_stages(self) -> tuple[StageRecord, ...]:
        """按权威排序顺序返回剧本包阶段。"""

        return tuple(sorted(self.package.stages, key=lambda stage: stage.sort_order))

    def apply_stage_runtime(self, state: GameState, stage: StageRecord) -> None:
        """将阶段可用动作、角色和场景写入状态。"""

        state["available_actions"] = text_list(stage.definition.get("available_actions"))
        state["available_characters"] = text_list(stage.definition.get("available_characters"))
        state["available_scenes"] = text_list(stage.definition.get("available_scenes"))
        if (
            len(state["available_scenes"]) > 0
            and state["current_scene"] not in state["available_scenes"]
        ):
            state["current_scene"] = state["available_scenes"][0]

    def matching_ending(self, state: GameState) -> EndingRecord | None:
        """返回按声明顺序首个条件匹配的结局。"""

        for ending in self.package.endings:
            if evaluate_condition(ending.condition, state):
                return ending
        return None

    def stage_exit_condition_met(self, state: GameState) -> bool:
        """返回当前阶段是否有任一退出条件匹配。"""

        stage = self.stage_by_id(state["current_stage"])
        for condition in json_mapping_list(stage.definition.get("exit_conditions")):
            if evaluate_condition(condition, state):
                return True
        return False

    def stage_entry_conditions_met(self, state: GameState, stage_id: str) -> bool:
        """返回目标阶段的全部进入条件是否均匹配。"""

        stage = self.stage_by_id(stage_id)
        conditions = json_mapping_list(stage.definition.get("entry_conditions"))
        return all(evaluate_condition(condition, state) for condition in conditions)

    def completed_act_for_stage(self, stage_id: str) -> str | None:
        """返回离开最后一个索引阶段时完成的幕。"""

        stage_index = stage_index_from_mapping(self.package.stage_index)
        for act in stage_index.acts:
            if len(act.stages) > 0 and act.stages[-1] == stage_id:
                return act.id
        return None


@dataclass(frozen=True, slots=True)
class StageLookupError(Exception):
    """报告已校验运行时剧本包中缺少某个阶段 ID。"""

    stage_id: str

    def __str__(self) -> str:
        return f"stage not found: {self.stage_id}"


@dataclass(frozen=True, slots=True)
class CharacterChapterLookupError(Exception):
    """报告已校验运行时剧本包中缺少某个人物章节 ID。"""

    chapter_id: str

    def __str__(self) -> str:
        return f"character chapter not found: {self.chapter_id}"


@dataclass(frozen=True, slots=True)
class ClueLookupError(Exception):
    """报告已校验运行时剧本包中缺少某个线索 ID。"""

    clue_id: str

    def __str__(self) -> str:
        return f"clue not found: {self.clue_id}"


def boolean_config(value: JsonValue | None) -> bool:
    """读取严格布尔配置值，并兼容旧版小写文本。"""

    match value:
        case bool() as flag:
            return flag
        case str() as text:
            return text.lower() == "true"
        case int() | float() | list() | dict() | None:
            return False


def record_dialog(state: GameState, character_id: str | None, text: str | None) -> None:
    """记录 NPC 对话次数和玩家的非空发言。"""

    if character_id is None:
        return
    state["character_dialog_counts"][character_id] = (
        state["character_dialog_counts"].get(character_id, 0) + 1
    )
    if text is not None:
        state["player_utterances"].append(text)


def record_evidence_presentation(state: GameState, target: str | None) -> None:
    """记录已校验的 evidence_id:character_id 出示目标。"""

    if target is None or ":" not in target:
        return
    evidence_id, character_id = target.split(":", maxsplit=1)
    state["evidences_shown_to_npcs"].append(
        {"evidence_id": evidence_id, "character_id": character_id},
    )


def text_list(value: JsonValue | None) -> list[str]:
    """从剧本包 JSON 列表中提取字符串值或动作 ID。"""

    if not isinstance(value, list):
        return []
    results: list[str] = []
    for item in value:
        if isinstance(item, str):
            results.append(item)
        elif isinstance(item, dict):
            action_id = item.get("id")
            if isinstance(action_id, str):
                results.append(action_id)
    return results
