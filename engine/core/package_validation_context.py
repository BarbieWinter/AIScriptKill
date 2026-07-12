"""收集带稳定来源路径的类型化剧本包校验问题。"""

from dataclasses import dataclass
from typing import Final

from engine.api.schemas.common import JsonValue
from engine.core.package_archive import PackageArchiveError

SUPPORTED_EVENT_ACTIONS: Final[frozenset[str]] = frozenset(
    (
        "clue_discover",
        "dm_narrate",
        "npc_emotion",
        "npc_enter_scene",
        "play_audio",
        "save_checkpoint",
        "show_truth_summary",
        "transition_to",
        "unlock_clue_round",
        "unlock_scenes",
    ),
)
ACTION_TYPES: Final[frozenset[str]] = frozenset(
    (
        "talk_to_npc",
        "examine_scene",
        "show_evidence",
        "use_card",
        "open_clue_board",
        "request_advance",
    ),
)


@dataclass(frozen=True, slots=True)
class PackageValidationContext:
    """保存跨文件校验器使用的权威 ID 和路径。"""

    stage_ids: frozenset[str]
    act_ids: frozenset[str]
    character_ids: frozenset[str]
    clue_ids: frozenset[str]
    evidence_ids: frozenset[str]
    scene_ids: frozenset[str]
    media_ids: frozenset[str]
    clue_round_ids: frozenset[str]
    ending_ids: frozenset[str]
    available_files: frozenset[str]
    card_ids: frozenset[str] = frozenset()
    event_ids: frozenset[str] = frozenset()
    deduction_chain_ids: frozenset[str] = frozenset()


def ensure_reference(owner: str, reference: str, known_ids: frozenset[str]) -> None:
    """要求引用的 ID 存在，否则抛出稳定的无效引用错误。"""

    if reference in known_ids:
        return
    raise PackageArchiveError(
        "PACKAGE_REFERENCE_INVALID",
        f"{owner} 指向不存在的对象: {reference}",
    )


def metadata_text(value: JsonValue | None) -> str | None:
    """仅在元数据值为非空文本时返回该值。"""

    if isinstance(value, str) and value != "":
        return value
    return None


def metadata_texts(value: JsonValue | None) -> tuple[str, ...]:
    """返回元数据列表中的非空文本项。"""

    if not isinstance(value, list):
        return ()
    return tuple(item for item in value if isinstance(item, str) and item != "")


def json_mapping_list(value: JsonValue | None) -> list[dict[str, JsonValue]]:
    """将可选 JSON 值校验为映射列表。"""

    if value is None:
        return []
    if not isinstance(value, list):
        raise PackageArchiveError(
            "PACKAGE_MAPPING_LIST_INVALID",
            "条件或事件集合必须是对象列表",
        )
    mappings: list[dict[str, JsonValue]] = []
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise PackageArchiveError(
                "PACKAGE_MAPPING_LIST_INVALID",
                f"条件或事件集合第 {index} 项必须是对象",
            )
        mappings.append(item)
    return mappings


def required_mapping(
    owner: str,
    mapping: dict[str, JsonValue],
    field: str,
) -> dict[str, JsonValue]:
    """读取必需的映射字段，否则抛出稳定的引用错误。"""

    value = mapping.get(field)
    if isinstance(value, dict):
        return value
    raise PackageArchiveError("PACKAGE_REFERENCE_INVALID", f"{owner} 缺少对象字段: {field}")


def required_text(owner: str, mapping: dict[str, JsonValue], field: str) -> str:
    """读取必需的非空文本字段，否则抛出稳定的引用错误。"""

    value = metadata_text(mapping.get(field))
    if value is not None:
        return value
    raise PackageArchiveError("PACKAGE_REFERENCE_INVALID", f"{owner} 缺少文本字段: {field}")
