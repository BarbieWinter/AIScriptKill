"""Keep the browser fixture aligned with the real multiplayer contract."""

from engine.tests.multiplayer_gameplay_contract_fixture import (
    OUTPUT_PATH,
    build_multiplayer_gameplay_contract,
    serialized_multiplayer_gameplay_contract,
)


def test_browser_gameplay_contract_fixture_is_current_and_participant_safe() -> None:
    contract = build_multiplayer_gameplay_contract()
    serialized = serialized_multiplayer_gameplay_contract()

    assert "\\r\\n" not in serialized
    assert b"\r\n" not in OUTPUT_PATH.read_bytes()
    assert OUTPUT_PATH.read_text(encoding="utf-8") == serialized
    final_host = contract["states"]["final_read"]["host"]
    assert [material["id"] for material in final_host["public_materials"]] == [
        "arrival-photo",
        "witness-note",
    ]
    serialized_host = str(contract["states"]["investigation_read"]["host"])
    assert "insider-investigation" not in serialized_host
    assert "private_by_member" not in serialized_host


def test_browser_gameplay_contract_covers_privacy_and_message_continuation() -> None:
    contract = build_multiplayer_gameplay_contract()
    forbidden_chapters = {
        "host": ("insider-investigation", "insider-final-judgment"),
        "guest": ("investigator-investigation", "investigator-final-judgment"),
    }
    for snapshots in contract["states"].values():
        for identity, snapshot in snapshots.items():
            serialized_snapshot = str(snapshot)
            assert "private_by_member" not in serialized_snapshot
            for chapter_id in forbidden_chapters[identity]:
                assert chapter_id not in serialized_snapshot

    message_transition = next(
        transition
        for transition in contract["transitions"]
        if transition["from"] == "investigation_message" and transition["type"] == "hint.request"
    )
    assert message_transition["event_sequence"] == 9
    assert "门锁没有损坏。" in str(contract["states"]["message_completed"]["guest"])
