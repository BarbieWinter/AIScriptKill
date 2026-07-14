from dataclasses import replace

from engine.core.package_schema import CharacterChapterRecord, JsonMapping
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


def test_chunk_package_does_not_index_character_chapter_content() -> None:
    package = replace(
        rag_package(),
        chapters=(
            CharacterChapterRecord(
                id="chapter-private",
                character_id="player",
                sort_order=1,
                title="私密章节",
                visibility="character_only",
                release={"type": "game_start"},
                stage_min="prologue",
                content="这段唯一文字不能进入当前普通 RAG 索引。",
            ),
        ),
    )

    chunks = chunk_package(package)

    assert all("这段唯一文字" not in chunk.text for chunk in chunks)


def test_chunk_package_excludes_negative_knowledge_and_evidence_text() -> None:
    package = rag_package()
    npc = package.characters[1]
    definition = dict(npc.definition)
    raw_knowledge = definition["knowledge"]
    assert isinstance(raw_knowledge, dict)
    knowledge: JsonMapping = dict(raw_knowledge)
    raw_prologue = knowledge["prologue"]
    assert isinstance(raw_prologue, dict)
    prologue: JsonMapping = dict(raw_prologue)
    prologue["doesnt_know"] = ["禁止检索的负面事实"]
    prologue["deny_facts"] = ["禁止检索的红线事实"]
    knowledge["prologue"] = prologue
    definition["knowledge"] = knowledge
    package = replace(
        package,
        characters=(package.characters[0], replace(npc, definition=definition)),
    )

    chunks = chunk_package(package)

    assert all("禁止检索的负面事实" not in chunk.text for chunk in chunks)
    assert all("禁止检索的红线事实" not in chunk.text for chunk in chunks)
    assert all(chunk.source_type != "evidence" for chunk in chunks)
    assert all(
        evidence.description_surface not in chunk.text
        for evidence in package.evidences
        for chunk in chunks
    )


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
