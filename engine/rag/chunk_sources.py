from collections.abc import Iterable

from engine.core.package_schema import (
    CharacterRecord,
    ClueRecord,
    EndingRecord,
    EvidenceRecord,
    JsonMapping,
    ScriptPackageImport,
    StageRecord,
)
from engine.rag.chunk_utils import json_summary, source_chunks, stage_order
from engine.rag.metadata import chunk_metadata, json_mapping, json_string_list, metadata_text
from engine.rag.models import RagChunk, RagVisibility


def package_context_chunks(
    package: ScriptPackageImport,
    entry_stage: str,
    stage_orders: dict[str, int],
    max_chars: int,
) -> tuple[RagChunk, ...]:
    info = json_mapping(package.package.config.get("info"))
    description = metadata_text(info, "description")
    text = "\n".join(item for item in (package.package.title, description) if item)
    metadata = chunk_metadata(
        script_id=package.package.id,
        source_type="script_context",
        visibility="public",
        stage_visible=entry_stage,
        stage_order=stage_order(stage_orders, entry_stage),
    )
    return source_chunks("script_context", "package", text, metadata, max_chars)


def stage_chunks(
    script_id: str,
    stages: tuple[StageRecord, ...],
    stage_orders: dict[str, int],
    max_chars: int,
) -> Iterable[RagChunk]:
    for stage in stages:
        description = metadata_text(stage.definition, "description")
        text = "\n".join(item for item in (stage.name, description) if item)
        metadata = chunk_metadata(
            script_id=script_id,
            source_type="script_context",
            visibility="public",
            stage_visible=stage.id,
            stage_order=stage_order(stage_orders, stage.id),
            extra={"stage_id": stage.id},
        )
        yield from source_chunks("script_context", f"stage:{stage.id}", text, metadata, max_chars)


def character_chunks(
    script_id: str,
    characters: tuple[CharacterRecord, ...],
    stage_orders: dict[str, int],
    max_chars: int,
) -> Iterable[RagChunk]:
    for character in characters:
        knowledge = json_mapping(character.definition.get("knowledge"))
        visibility: RagVisibility = "dm_only" if character.is_dm_alter_ego else "character_only"
        for stage_id, stage_knowledge in knowledge.items():
            stage_mapping = json_mapping(stage_knowledge)
            lines = [
                f"角色: {character.name}",
                *json_string_list(stage_mapping.get("knows")),
                *json_string_list(stage_mapping.get("doesnt_know")),
            ]
            metadata = chunk_metadata(
                script_id=script_id,
                source_type="character_knowledge",
                visibility=visibility,
                stage_visible=stage_id,
                stage_order=stage_order(stage_orders, stage_id),
                character_id=character.id,
                extra={"stage_id": stage_id},
            )
            source_id = f"{character.id}:{stage_id}"
            yield from source_chunks(
                "character_knowledge",
                source_id,
                "\n".join(lines),
                metadata,
                max_chars,
            )


def clue_chunks(
    script_id: str,
    clues: tuple[ClueRecord, ...],
    stage_orders: dict[str, int],
    entry_stage: str,
    max_chars: int,
) -> Iterable[RagChunk]:
    for clue in clues:
        stage_visible = metadata_text(clue.metadata, "stage_visible", entry_stage)
        metadata = chunk_metadata(
            script_id=script_id,
            source_type="clue",
            visibility="public",
            stage_visible=stage_visible,
            stage_order=stage_order(stage_orders, stage_visible),
            importance=clue.importance,
            extra={"clue_id": clue.id, "round_id": clue.round_id},
        )
        text = "\n".join((clue.name, clue.description))
        yield from source_chunks("clue", clue.id, text, metadata, max_chars)


def evidence_chunks(
    script_id: str,
    evidences: tuple[EvidenceRecord, ...],
    stage_orders: dict[str, int],
    entry_stage: str,
    max_chars: int,
) -> Iterable[RagChunk]:
    for evidence in evidences:
        metadata = chunk_metadata(
            script_id=script_id,
            source_type="evidence",
            visibility="public",
            stage_visible=entry_stage,
            stage_order=stage_order(stage_orders, entry_stage),
            extra={"evidence_id": evidence.id, "segment": "surface"},
        )
        yield from source_chunks(
            "evidence",
            f"{evidence.id}:surface",
            "\n".join((evidence.name, evidence.description_surface)),
            metadata,
            max_chars,
        )
        if evidence.description_deep:
            dm_metadata = chunk_metadata(
                script_id=script_id,
                source_type="evidence",
                visibility="dm_only",
                stage_visible=entry_stage,
                stage_order=stage_order(stage_orders, entry_stage),
                extra={"evidence_id": evidence.id, "segment": "deep"},
            )
            yield from source_chunks(
                "evidence",
                f"{evidence.id}:deep",
                "\n".join((evidence.name, evidence.description_deep)),
                dm_metadata,
                max_chars,
            )


def ending_chunks(
    script_id: str,
    endings: tuple[EndingRecord, ...],
    entry_stage: str,
    stage_orders: dict[str, int],
    max_chars: int,
) -> Iterable[RagChunk]:
    for ending in endings:
        text = "\n".join(
            (
                f"结局: {ending.name}",
                metadata_text(ending.metadata, "outcome_text"),
                f"触发条件: {json_summary(ending.condition)}",
                f"触发事件: {json_summary(list(ending.on_trigger))}",
            ),
        )
        metadata = chunk_metadata(
            script_id=script_id,
            source_type="script_context",
            visibility="dm_only",
            stage_visible=entry_stage,
            stage_order=stage_order(stage_orders, entry_stage),
            importance=100,
            extra={"ending_id": ending.id, "segment": "ending_truth"},
        )
        yield from source_chunks(
            "script_context",
            f"ending:{ending.id}",
            text,
            metadata,
            max_chars,
        )


def dm_guide_chunks(
    script_id: str,
    dm_guide: JsonMapping,
    entry_stage: str,
    stage_orders: dict[str, int],
    max_chars: int,
) -> Iterable[RagChunk]:
    for guide_key, guide_content in dm_guide.items():
        metadata = chunk_metadata(
            script_id=script_id,
            source_type="script_context",
            visibility="dm_only",
            stage_visible=entry_stage,
            stage_order=stage_order(stage_orders, entry_stage),
            importance=100,
            extra={"guide_key": guide_key, "segment": "dm_guide"},
        )
        yield from source_chunks(
            "script_context",
            f"dm_guide:{guide_key}",
            json_summary(guide_content),
            metadata,
            max_chars,
        )
