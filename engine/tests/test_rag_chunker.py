from engine.rag.chunker import chunk_package
from engine.rag.metadata import metadata_int, metadata_text
from engine.tests.rag_fixtures import rag_package


def test_chunk_package_adds_security_metadata_to_every_chunk() -> None:
    chunks = chunk_package(rag_package())

    assert len(chunks) > 0
    assert all(chunk.script_id == "minimal-case" for chunk in chunks)
    assert all(metadata_text(chunk.metadata, "script_id") == "minimal-case" for chunk in chunks)
    assert all(metadata_text(chunk.metadata, "visibility") for chunk in chunks)
    assert all(metadata_text(chunk.metadata, "stage_visible") for chunk in chunks)


def test_chunk_package_marks_truth_material_dm_only() -> None:
    chunks = chunk_package(rag_package())

    truth_chunks = tuple(chunk for chunk in chunks if "NPC角色是凶手" in chunk.text)

    assert len(truth_chunks) > 0
    assert all(metadata_text(chunk.metadata, "visibility") == "dm_only" for chunk in truth_chunks)
    assert all(metadata_int(chunk.metadata, "importance") == 100 for chunk in truth_chunks)


def test_chunk_package_preserves_clue_stage_and_character_scope() -> None:
    chunks = chunk_package(rag_package())

    clue = next(
        chunk for chunk in chunks if chunk.source_type == "clue" and chunk.source_id == "clue_1"
    )
    player_knowledge = next(
        chunk
        for chunk in chunks
        if chunk.source_type == "character_knowledge" and chunk.source_id == "player:act1"
    )

    assert metadata_text(clue.metadata, "stage_visible") == "act1"
    assert metadata_int(clue.metadata, "stage_order") == 10
    assert metadata_text(player_knowledge.metadata, "visibility") == "character_only"
    assert metadata_text(player_knowledge.metadata, "character_id") == "player"
