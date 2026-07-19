"""Encode immutable, runtime-authoritative script package snapshots."""

from __future__ import annotations

import json
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from hashlib import sha256
from hmac import compare_digest
from typing import Final, cast

from engine.api.schemas.common import JsonValue
from engine.api.schemas.packages import PackageStatus
from engine.core.package_schema import (
    CharacterChapterRecord,
    CharacterRecord,
    ClueRecord,
    EndingRecord,
    EvidenceRecord,
    JsonMapping,
    MediaRecord,
    MediaType,
    PackageRecord,
    SceneRecord,
    ScriptPackageImport,
    StageRecord,
)

SNAPSHOT_SCHEMA_VERSION: Final = 1
_SHA256_PATTERN: Final = re.compile(r"^[0-9a-f]{64}$")
_SNAPSHOT_FIELDS: Final = frozenset(
    {
        "snapshot_schema_version",
        "package",
        "stages",
        "characters",
        "chapters",
        "clues",
        "evidences",
        "scenes",
        "media_assets",
        "endings",
        "stage_index",
        "dm_guide",
    }
)


@dataclass(frozen=True, slots=True)
class RuntimePackageSnapshot:
    """A JSONB-ready package snapshot and its canonical SHA-256 digest."""

    payload: JsonMapping
    sha256: str

    @property
    def digest(self) -> str:
        """Compatibility name for callers that describe SHA-256 as a digest."""

        return self.sha256

    @property
    def package_id(self) -> str:
        """Return the snapshotted package ID without decoding runtime records."""

        package = self.payload.get("package")
        if isinstance(package, dict):
            package_id = package.get("id")
            if isinstance(package_id, str):
                return package_id
        raise RuntimePackageSnapshotError("snapshot.package.id")

    @property
    def package_version(self) -> str:
        """Return the snapshotted package version without decoding runtime records."""

        package = self.payload.get("package")
        if isinstance(package, dict):
            package_version = package.get("version")
            if isinstance(package_version, str):
                return package_version
        raise RuntimePackageSnapshotError("snapshot.package.version")


def encode_runtime_package_snapshot(package: ScriptPackageImport) -> RuntimePackageSnapshot:
    """Encode all runtime-authoritative records, excluding archive assets and warnings."""

    payload = runtime_package_snapshot_payload(package)
    canonical = _canonical_json_bytes(payload)
    return RuntimePackageSnapshot(payload=payload, sha256=sha256(canonical).hexdigest())


def runtime_package_snapshot_payload(package: ScriptPackageImport) -> JsonMapping:
    """Build the versioned JSON payload stored in the session snapshot column."""

    payload: dict[str, object] = {
        "snapshot_schema_version": SNAPSHOT_SCHEMA_VERSION,
        "package": {
            "id": package.package.id,
            "title": package.package.title,
            "version": package.package.version,
            "status": package.package.status,
            "config": _copy_json_mapping(package.package.config, "package.config"),
        },
        "stages": [
            {
                "id": record.id,
                "name": record.name,
                "sort_order": record.sort_order,
                "definition": _copy_json_mapping(record.definition, "stage.definition"),
            }
            for record in package.stages
        ],
        "characters": [
            {
                "id": record.id,
                "name": record.name,
                "definition": _copy_json_mapping(record.definition, "character.definition"),
                "is_playable": record.is_playable,
                "is_dm_alter_ego": record.is_dm_alter_ego,
                "sort_order": record.sort_order,
            }
            for record in package.characters
        ],
        "chapters": [
            {
                "id": record.id,
                "character_id": record.character_id,
                "sort_order": record.sort_order,
                "title": record.title,
                "visibility": record.visibility,
                "release": _copy_json_mapping(record.release, "chapter.release"),
                "stage_min": record.stage_min,
                "content": record.content,
            }
            for record in package.chapters
        ],
        "clues": [
            {
                "id": record.id,
                "name": record.name,
                "round_id": record.round_id,
                "image_url": record.image_url,
                "description": record.description,
                "is_key": record.is_key,
                "importance": record.importance,
                "metadata": _copy_json_mapping(record.metadata, "clue.metadata"),
            }
            for record in package.clues
        ],
        "evidences": [
            {
                "id": record.id,
                "name": record.name,
                "image_url": record.image_url,
                "description_surface": record.description_surface,
                "description_deep": record.description_deep,
                "type": record.type,
                "metadata": _copy_json_mapping(record.metadata, "evidence.metadata"),
            }
            for record in package.evidences
        ],
        "scenes": [
            {
                "id": record.id,
                "name": record.name,
                "background_url": record.background_url,
                "definition": _copy_json_mapping(record.definition, "scene.definition"),
            }
            for record in package.scenes
        ],
        "media_assets": [
            {
                "id": record.id,
                "type": record.type,
                "file_url": record.file_url,
                "subtitle_url": record.subtitle_url,
                "duration_sec": record.duration_sec,
                "metadata": _copy_json_mapping(record.metadata, "media.metadata"),
            }
            for record in package.media_assets
        ],
        "endings": [
            {
                "id": record.id,
                "name": record.name,
                "condition": _copy_json_mapping(record.condition, "ending.condition"),
                "on_trigger": [
                    _copy_json_mapping(action, "ending.on_trigger") for action in record.on_trigger
                ],
                "metadata": _copy_json_mapping(record.metadata, "ending.metadata"),
            }
            for record in package.endings
        ],
        "stage_index": _copy_json_mapping(package.stage_index, "stage_index"),
        "dm_guide": _copy_json_mapping(package.dm_guide, "dm_guide"),
    }
    # Validate primitive dataclass fields too, not only their arbitrary JSON mappings.
    return _copy_json_mapping(payload, "snapshot")


def canonical_runtime_package_bytes(package: ScriptPackageImport) -> bytes:
    """Return stable compact sorted-key UTF-8 JSON for a runtime package."""

    return _canonical_json_bytes(runtime_package_snapshot_payload(package))


def runtime_package_sha256(package: ScriptPackageImport) -> str:
    """Return the lowercase SHA-256 digest of a package's canonical snapshot."""

    return sha256(canonical_runtime_package_bytes(package)).hexdigest()


def decode_runtime_package_snapshot(
    payload: Mapping[str, object],
    expected_sha256: str,
    *,
    expected_package_id: str | None = None,
    expected_package_version: str | None = None,
) -> ScriptPackageImport:
    """Verify a JSONB snapshot digest and strictly rebuild runtime package records."""

    if _SHA256_PATTERN.fullmatch(expected_sha256) is None:
        raise RuntimePackageSnapshotError("sha256")
    copied_payload = _copy_json_mapping(payload, "snapshot")
    actual_sha256 = sha256(_canonical_json_bytes(copied_payload)).hexdigest()
    if not compare_digest(actual_sha256, expected_sha256):
        raise RuntimePackageSnapshotError("sha256")

    snapshot = _record(copied_payload, _SNAPSHOT_FIELDS, "snapshot")
    if _required_int(snapshot, "snapshot_schema_version", "snapshot") != SNAPSHOT_SCHEMA_VERSION:
        raise RuntimePackageSnapshotError("snapshot.snapshot_schema_version")

    package = _decode_package(snapshot["package"])
    if expected_package_id is not None and package.id != expected_package_id:
        raise RuntimePackageSnapshotError("snapshot.package.id")
    if expected_package_version is not None and package.version != expected_package_version:
        raise RuntimePackageSnapshotError("snapshot.package.version")

    return ScriptPackageImport(
        package=package,
        stages=tuple(
            _decode_stage(item, index)
            for index, item in enumerate(_required_list(snapshot, "stages", "snapshot"))
        ),
        characters=tuple(
            _decode_character(item, index)
            for index, item in enumerate(_required_list(snapshot, "characters", "snapshot"))
        ),
        chapters=tuple(
            _decode_chapter(item, index)
            for index, item in enumerate(_required_list(snapshot, "chapters", "snapshot"))
        ),
        clues=tuple(
            _decode_clue(item, index)
            for index, item in enumerate(_required_list(snapshot, "clues", "snapshot"))
        ),
        evidences=tuple(
            _decode_evidence(item, index)
            for index, item in enumerate(_required_list(snapshot, "evidences", "snapshot"))
        ),
        scenes=tuple(
            _decode_scene(item, index)
            for index, item in enumerate(_required_list(snapshot, "scenes", "snapshot"))
        ),
        media_assets=tuple(
            _decode_media(item, index)
            for index, item in enumerate(_required_list(snapshot, "media_assets", "snapshot"))
        ),
        endings=tuple(
            _decode_ending(item, index)
            for index, item in enumerate(_required_list(snapshot, "endings", "snapshot"))
        ),
        stage_index=_required_mapping(snapshot, "stage_index", "snapshot"),
        dm_guide=_required_mapping(snapshot, "dm_guide", "snapshot"),
    )


def _decode_package(raw: object) -> PackageRecord:
    path = "snapshot.package"
    record = _record(raw, frozenset({"id", "title", "version", "status", "config"}), path)
    status_value = _required_text(record, "status", path)
    if status_value not in ("draft", "importing", "published", "archived"):
        raise RuntimePackageSnapshotError(f"{path}.status")
    status: PackageStatus = status_value
    return PackageRecord(
        id=_required_text(record, "id", path),
        title=_required_text(record, "title", path),
        version=_required_text(record, "version", path),
        status=status,
        config=_required_mapping(record, "config", path),
    )


def _decode_stage(raw: object, index: int) -> StageRecord:
    path = f"snapshot.stages[{index}]"
    record = _record(raw, frozenset({"id", "name", "sort_order", "definition"}), path)
    return StageRecord(
        id=_required_text(record, "id", path),
        name=_required_text(record, "name", path),
        sort_order=_required_int(record, "sort_order", path),
        definition=_required_mapping(record, "definition", path),
    )


def _decode_character(raw: object, index: int) -> CharacterRecord:
    path = f"snapshot.characters[{index}]"
    record = _record(
        raw,
        frozenset({"id", "name", "definition", "is_playable", "is_dm_alter_ego", "sort_order"}),
        path,
    )
    return CharacterRecord(
        id=_required_text(record, "id", path),
        name=_required_text(record, "name", path),
        definition=_required_mapping(record, "definition", path),
        is_playable=_required_bool(record, "is_playable", path),
        is_dm_alter_ego=_required_bool(record, "is_dm_alter_ego", path),
        sort_order=_required_int(record, "sort_order", path),
    )


def _decode_chapter(raw: object, index: int) -> CharacterChapterRecord:
    path = f"snapshot.chapters[{index}]"
    record = _record(
        raw,
        frozenset(
            {
                "id",
                "character_id",
                "sort_order",
                "title",
                "visibility",
                "release",
                "stage_min",
                "content",
            }
        ),
        path,
    )
    if _required_text(record, "visibility", path) != "character_only":
        raise RuntimePackageSnapshotError(f"{path}.visibility")
    return CharacterChapterRecord(
        id=_required_text(record, "id", path),
        character_id=_required_text(record, "character_id", path),
        sort_order=_required_int(record, "sort_order", path),
        title=_required_text(record, "title", path),
        visibility="character_only",
        release=_required_mapping(record, "release", path),
        stage_min=_optional_text(record, "stage_min", path),
        content=_required_text(record, "content", path),
    )


def _decode_clue(raw: object, index: int) -> ClueRecord:
    path = f"snapshot.clues[{index}]"
    record = _record(
        raw,
        frozenset(
            {
                "id",
                "name",
                "round_id",
                "image_url",
                "description",
                "is_key",
                "importance",
                "metadata",
            }
        ),
        path,
    )
    return ClueRecord(
        id=_required_text(record, "id", path),
        name=_required_text(record, "name", path),
        round_id=_required_text(record, "round_id", path),
        image_url=_optional_text(record, "image_url", path),
        description=_required_text(record, "description", path),
        is_key=_required_bool(record, "is_key", path),
        importance=_required_int(record, "importance", path),
        metadata=_required_mapping(record, "metadata", path),
    )


def _decode_evidence(raw: object, index: int) -> EvidenceRecord:
    path = f"snapshot.evidences[{index}]"
    record = _record(
        raw,
        frozenset(
            {
                "id",
                "name",
                "image_url",
                "description_surface",
                "description_deep",
                "type",
                "metadata",
            }
        ),
        path,
    )
    return EvidenceRecord(
        id=_required_text(record, "id", path),
        name=_required_text(record, "name", path),
        image_url=_optional_text(record, "image_url", path),
        description_surface=_required_text(record, "description_surface", path),
        description_deep=_optional_text(record, "description_deep", path),
        type=_required_text(record, "type", path),
        metadata=_required_mapping(record, "metadata", path),
    )


def _decode_scene(raw: object, index: int) -> SceneRecord:
    path = f"snapshot.scenes[{index}]"
    record = _record(raw, frozenset({"id", "name", "background_url", "definition"}), path)
    return SceneRecord(
        id=_required_text(record, "id", path),
        name=_required_text(record, "name", path),
        background_url=_optional_text(record, "background_url", path),
        definition=_required_mapping(record, "definition", path),
    )


def _decode_media(raw: object, index: int) -> MediaRecord:
    path = f"snapshot.media_assets[{index}]"
    record = _record(
        raw,
        frozenset({"id", "type", "file_url", "subtitle_url", "duration_sec", "metadata"}),
        path,
    )
    media_type_value = _required_text(record, "type", path)
    if media_type_value not in ("bgm", "story", "sfx", "voice", "image", "video"):
        raise RuntimePackageSnapshotError(f"{path}.type")
    media_type: MediaType = media_type_value
    return MediaRecord(
        id=_required_text(record, "id", path),
        type=media_type,
        file_url=_required_text(record, "file_url", path),
        subtitle_url=_optional_text(record, "subtitle_url", path),
        duration_sec=_optional_number(record, "duration_sec", path),
        metadata=_required_mapping(record, "metadata", path),
    )


def _decode_ending(raw: object, index: int) -> EndingRecord:
    path = f"snapshot.endings[{index}]"
    record = _record(
        raw,
        frozenset({"id", "name", "condition", "on_trigger", "metadata"}),
        path,
    )
    actions = _required_list(record, "on_trigger", path)
    return EndingRecord(
        id=_required_text(record, "id", path),
        name=_required_text(record, "name", path),
        condition=_required_mapping(record, "condition", path),
        on_trigger=tuple(
            _mapping_value(action, f"{path}.on_trigger[{action_index}]")
            for action_index, action in enumerate(actions)
        ),
        metadata=_required_mapping(record, "metadata", path),
    )


def _record(raw: object, fields: frozenset[str], path: str) -> dict[str, object]:
    if not isinstance(raw, dict):
        raise RuntimePackageSnapshotError(path)
    mapping = cast(dict[object, object], raw)
    if any(not isinstance(key, str) for key in mapping):
        raise RuntimePackageSnapshotError(path)
    typed = cast(dict[str, object], mapping)
    missing = fields.difference(typed)
    if missing:
        raise RuntimePackageSnapshotError(f"{path}.{min(missing)}")
    if set(typed).difference(fields):
        raise RuntimePackageSnapshotError(path)
    return typed


def _required_text(record: Mapping[str, object], key: str, path: str) -> str:
    value = record[key]
    if not isinstance(value, str):
        raise RuntimePackageSnapshotError(f"{path}.{key}")
    return value


def _optional_text(record: Mapping[str, object], key: str, path: str) -> str | None:
    value = record[key]
    if value is None or isinstance(value, str):
        return value
    raise RuntimePackageSnapshotError(f"{path}.{key}")


def _required_int(record: Mapping[str, object], key: str, path: str) -> int:
    value = record[key]
    if type(value) is not int:
        raise RuntimePackageSnapshotError(f"{path}.{key}")
    return value


def _required_bool(record: Mapping[str, object], key: str, path: str) -> bool:
    value = record[key]
    if type(value) is not bool:
        raise RuntimePackageSnapshotError(f"{path}.{key}")
    return value


def _optional_number(record: Mapping[str, object], key: str, path: str) -> float | None:
    value = record[key]
    if value is None:
        return None
    if type(value) not in (int, float) or not math.isfinite(cast(float, value)):
        raise RuntimePackageSnapshotError(f"{path}.{key}")
    return float(cast(int | float, value))


def _required_list(record: Mapping[str, object], key: str, path: str) -> list[object]:
    value = record[key]
    if not isinstance(value, list):
        raise RuntimePackageSnapshotError(f"{path}.{key}")
    return cast(list[object], value)


def _required_mapping(record: Mapping[str, object], key: str, path: str) -> JsonMapping:
    return _mapping_value(record[key], f"{path}.{key}")


def _mapping_value(value: object, path: str) -> JsonMapping:
    if not isinstance(value, dict):
        raise RuntimePackageSnapshotError(path)
    mapping = cast(dict[object, object], value)
    if any(not isinstance(key, str) for key in mapping):
        raise RuntimePackageSnapshotError(f"{path}.json_key")
    return _copy_json_mapping(cast(dict[str, object], mapping), path)


def _copy_json_mapping(value: Mapping[str, object], path: str) -> JsonMapping:
    result: JsonMapping = {}
    for key, item in value.items():
        result[key] = _copy_json_value(item, f"{path}.{key}")
    return result


def _copy_json_value(value: object, path: str) -> JsonValue:
    if value is None or type(value) in (str, int, bool):
        return cast(str | int | bool | None, value)
    if type(value) is float:
        number = value
        if not math.isfinite(number):
            raise RuntimePackageSnapshotError(f"{path}.json_number")
        return number
    if isinstance(value, list):
        items = cast(list[object], value)
        return [_copy_json_value(item, f"{path}[{index}]") for index, item in enumerate(items)]
    if isinstance(value, dict):
        return _mapping_value(cast(dict[object, object], value), path)
    raise RuntimePackageSnapshotError(f"{path}.json_value")


def _canonical_json_bytes(payload: Mapping[str, object]) -> bytes:
    try:
        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except (TypeError, ValueError) as error:
        raise RuntimePackageSnapshotError("snapshot.json") from error
    return encoded.encode("utf-8")


class RuntimePackageSnapshotError(ValueError):
    """Report an invalid package snapshot field or digest."""

    def __init__(self, field: str) -> None:
        super().__init__(f"invalid runtime package snapshot field: {field}")
        self.field = field
