from engine.rag.metadata import metadata_int, metadata_text
from engine.rag.models import RagChunk, RagSessionContext


def is_chunk_visible(chunk: RagChunk, context: RagSessionContext) -> bool:
    if chunk.script_id != context.script_id:
        return False
    if metadata_int(chunk.metadata, "stage_order", 0) > context.current_stage_order:
        return False
    if context.is_dm:
        return True
    visibility = metadata_text(chunk.metadata, "visibility")
    if visibility == "public":
        return _is_unlocked_player_chunk(chunk, context)
    if visibility == "character_only":
        return _character_scope_matches(chunk, context) and _is_unlocked_player_chunk(
            chunk,
            context,
        )
    return False


def _character_scope_matches(chunk: RagChunk, context: RagSessionContext) -> bool:
    character_id = metadata_text(chunk.metadata, "character_id")
    if chunk.source_type == "character_knowledge":
        return (
            context.speaker_character_id is not None
            and character_id == context.speaker_character_id
        )
    return character_id == context.viewer_character_id


def _is_unlocked_player_chunk(chunk: RagChunk, context: RagSessionContext) -> bool:
    if chunk.source_type != "clue":
        return True
    return chunk.source_id in context.unlocked_clue_ids
