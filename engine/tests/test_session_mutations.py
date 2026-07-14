import engine.repositories.session_mutations as session_mutations
from engine.repositories.session_models import SessionRuntimeState


def test_session_state_patch_merges_progress_lists_monotonically() -> None:
    state = SessionRuntimeState(
        unlocked_clues=["clue-1"],
        discovered_evidences=["evidence-1"],
        unlocked_character_chapters=["chapter-1"],
    )

    merged = session_mutations._merge_state_patch(  # pyright: ignore[reportPrivateUsage]
        state,
        {
            "unlocked_clues": ["clue-2"],
            "discovered_evidences": ["evidence-2"],
            "unlocked_character_chapters": ["chapter-2"],
            "current_scene": "back-alley",
        },
    )

    assert merged.unlocked_clues == ["clue-1", "clue-2"]
    assert merged.discovered_evidences == ["evidence-1", "evidence-2"]
    assert merged.unlocked_character_chapters == ["chapter-1", "chapter-2"]
    assert merged.current_scene == "back-alley"


def test_checkpoint_progress_merge_cannot_relock_viewed_content() -> None:
    checkpoint = SessionRuntimeState(
        discovered_evidences=["evidence-1"],
        unlocked_character_chapters=["chapter-1"],
    )
    current = SessionRuntimeState(
        discovered_evidences=["evidence-1"],
        viewed_evidences=["evidence-1"],
        unlocked_character_chapters=["chapter-1"],
        read_character_chapters=["chapter-1"],
    )

    restored = session_mutations._merge_monotonic_progress(  # pyright: ignore[reportPrivateUsage]
        checkpoint,
        current,
    )

    assert restored.viewed_evidences == ["evidence-1"]
    assert restored.read_character_chapters == ["chapter-1"]
