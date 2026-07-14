from engine.core.package_schema import ScriptPackageImport
from engine.rag.chunk_sources import (
    character_chunks,
    clue_chunks,
    dm_guide_chunks,
    ending_chunks,
    package_context_chunks,
    stage_chunks,
)
from engine.rag.metadata import json_mapping, metadata_text
from engine.rag.models import RagChunk


def chunk_package(package: ScriptPackageImport, max_chars: int = 800) -> tuple[RagChunk, ...]:
    stage_orders = {stage.id: stage.sort_order for stage in package.stages}
    entry_stage = _entry_stage(package, stage_orders)
    script_id = package.package.id
    chunks: list[RagChunk] = []
    chunks.extend(package_context_chunks(package, entry_stage, stage_orders, max_chars))
    chunks.extend(stage_chunks(script_id, package.stages, stage_orders, max_chars))
    chunks.extend(character_chunks(script_id, package.characters, stage_orders, max_chars))
    chunks.extend(clue_chunks(script_id, package.clues, stage_orders, entry_stage, max_chars))
    chunks.extend(ending_chunks(script_id, package.endings, entry_stage, stage_orders, max_chars))
    chunks.extend(
        dm_guide_chunks(script_id, package.dm_guide, entry_stage, stage_orders, max_chars),
    )
    return tuple(chunks)


def _entry_stage(package: ScriptPackageImport, stage_orders: dict[str, int]) -> str:
    engine = json_mapping(package.package.config.get("engine"))
    entry_stage = metadata_text(engine, "entry_stage")
    if entry_stage:
        return entry_stage
    if len(stage_orders) == 0:
        return "prologue"
    return min(stage_orders, key=lambda stage_id: stage_orders[stage_id])
