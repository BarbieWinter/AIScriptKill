from collections.abc import Iterable
from typing import Final, assert_never

from engine.api.schemas.common import JsonValue
from engine.core.package_archive import PackageArchiveError
from engine.core.package_schema import (
    CharacterRecord,
    ClueRecord,
    EndingRecord,
    EvidenceRecord,
    JsonMapping,
    MediaRecord,
    MediaType,
    SceneRecord,
    StageRecord,
)
from engine.core.package_stage_index import StageIndexItem
from engine.core.package_yaml import (
    CharacterDefinition,
    CharacterIndexItem,
    ClueRoundDefinition,
    EndingFileDefinition,
    EvidenceDefinition,
    MediaAsset,
    MediaFileDefinition,
    SceneDefinition,
    StageActionDefinition,
    StageDefinition,
)

MEDIA_TYPES: Final[frozenset[MediaType]] = frozenset(
    ("bgm", "story", "sfx", "voice", "image", "video"),
)


def stage_record_from_mapping(
    raw: JsonMapping,
    index_item: StageIndexItem,
    act_id: str | None,
) -> StageRecord:
    stage = StageDefinition.model_validate(raw)
    return StageRecord(
        id=stage.id,
        name=index_item.name,
        sort_order=index_item.sort_order,
        definition=_stage_definition_mapping(raw, stage, index_item, act_id),
    )


def character_record_from_mapping(
    raw: JsonMapping,
    index_item: CharacterIndexItem,
) -> CharacterRecord:
    character = CharacterDefinition.model_validate(raw)
    return CharacterRecord(
        id=character.id,
        name=character.name,
        definition=raw,
        is_playable=index_item.playable,
        is_dm_alter_ego=character.is_dm_alter_ego or index_item.is_dm_alter_ego,
        sort_order=index_item.order,
    )


def clue_records_from_mapping(raw: JsonMapping) -> tuple[ClueRecord, ...]:
    clue_round = ClueRoundDefinition.model_validate(raw)
    return tuple(_clue_records(clue_round))


def evidence_record_from_mapping(raw: JsonMapping) -> EvidenceRecord:
    evidence = EvidenceDefinition.model_validate(raw)
    return EvidenceRecord(
        id=evidence.id,
        name=evidence.name,
        image_url=evidence.visual.image,
        description_surface=evidence.description.surface,
        description_deep=evidence.description.deep,
        type=evidence.type,
        metadata=raw,
    )


def scene_record_from_mapping(raw: JsonMapping) -> SceneRecord:
    scene = SceneDefinition.model_validate(raw)
    return SceneRecord(
        id=scene.id,
        name=scene.name,
        background_url=scene.visual.background,
        definition=raw,
    )


def media_records_from_mapping(raw: JsonMapping) -> tuple[MediaRecord, ...]:
    media_file = MediaFileDefinition.model_validate(raw)
    return (*_audio_records(media_file.audio_assets), *_image_records(media_file.image_assets))


def ending_records_from_mapping(raw: JsonMapping) -> tuple[EndingRecord, ...]:
    ending_file = EndingFileDefinition.model_validate(raw)
    raw_endings = _json_mapping_list(raw.get("endings"))
    return tuple(
        EndingRecord(
            id=ending.id,
            name=ending.name,
            condition=_required_mapping(raw_endings[index], "condition"),
            on_trigger=tuple(_json_mapping_list(raw_endings[index].get("on_trigger"))),
            metadata=raw_endings[index],
        )
        for index, ending in enumerate(ending_file.endings)
    )


def _stage_definition_mapping(
    raw: JsonMapping,
    stage: StageDefinition,
    index_item: StageIndexItem,
    act_id: str | None,
) -> JsonMapping:
    normalized = dict(raw)
    normalized["name"] = index_item.name
    normalized["sort_order"] = index_item.sort_order
    if len(index_item.meta) > 0:
        normalized["meta"] = index_item.meta
    if act_id is not None and normalized.get("act_id") is None:
        normalized["act_id"] = act_id
    action_ids: list[JsonValue] = []
    action_definitions: list[JsonValue] = []
    for action in stage.available_actions:
        match action:
            case str() as action_id:
                action_ids.append(action_id)
            case StageActionDefinition(id=action_id, label=label, description=description):
                action_ids.append(action_id)
                action_definitions.append(
                    {
                        "id": action_id,
                        "label": label,
                        "description": description,
                    },
                )
            case unreachable:
                assert_never(unreachable)
    normalized["available_actions"] = action_ids
    if len(action_definitions) > 0:
        normalized["action_definitions"] = action_definitions
    return normalized


def _clue_records(clue_round: ClueRoundDefinition) -> Iterable[ClueRecord]:
    for clue in clue_round.clues:
        related_characters: list[JsonValue] = [character for character in clue.related_characters]
        metadata: JsonMapping = {
            "stage_visible": clue.stage_visible or clue_round.stage_visible,
            "visibility": "public",
            "round_name": clue_round.name,
            "related_scene": clue.related_scene,
            "related_characters": related_characters,
        }
        yield ClueRecord(
            id=clue.id,
            name=clue.name,
            round_id=clue_round.round_id,
            image_url=clue.image,
            description=clue.description,
            is_key=clue.key_clue,
            importance=clue.importance,
            metadata=metadata,
        )


def _audio_records(assets: list[MediaAsset]) -> Iterable[MediaRecord]:
    for asset in assets:
        yield MediaRecord(
            id=asset.id,
            type=_media_type(asset.type),
            file_url=asset.file,
            subtitle_url=asset.subtitle_file,
            duration_sec=asset.duration_sec,
            metadata=asset.model_dump(mode="json"),
        )


def _image_records(assets: list[MediaAsset]) -> Iterable[MediaRecord]:
    for asset in assets:
        metadata = asset.model_dump(mode="json")
        metadata["original_type"] = asset.type
        yield MediaRecord(
            id=asset.id,
            type="image",
            file_url=asset.file,
            subtitle_url=None,
            duration_sec=asset.duration_sec,
            metadata=metadata,
        )


def _media_type(value: str) -> MediaType:
    if value not in MEDIA_TYPES:
        raise PackageArchiveError("INVALID_MEDIA_TYPE", f"不支持的媒体类型: {value}")
    return value


def _json_mapping_list(value: JsonValue | None) -> list[JsonMapping]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _required_mapping(mapping: JsonMapping, key: str) -> JsonMapping:
    value = mapping.get(key)
    if isinstance(value, dict):
        return value
    raise PackageArchiveError("INVALID_PACKAGE_SCHEMA", f"endings.yml endings[].{key} 必须是对象")
