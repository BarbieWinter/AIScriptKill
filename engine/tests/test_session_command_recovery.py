from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from engine.core.game_state import create_initial_state
from engine.repositories.session_command_models import CommandReceipt
from engine.repositories.session_command_state import (
    canonical_game_state_payload,
    game_state_from_payload,
    game_state_sha256,
)


def test_command_receipt_carries_recovery_fence_and_lineage() -> None:
    timestamp = datetime(2026, 7, 19, tzinfo=UTC)
    receipt = CommandReceipt(
        session_id=UUID("00000000-0000-4000-8000-000000000001"),
        command_id=UUID("00000000-0000-4000-8000-000000000002"),
        request_payload={"action": "open_clue_board", "expected_revision": 0},
        request_sha256="a" * 64,
        status="processing",
        expected_revision=0,
        base_revision=0,
        base_state={"session_id": "session"},
        base_state_sha256="b" * 64,
        result_revision=None,
        result=None,
        error_code=None,
        error_details={},
        base_checkpoint_id="base",
        checkpoint_id=None,
        state_sha256=None,
        event_sequence_from=None,
        event_sequence_to=None,
        attempt_count=2,
        lease_expires_at=timestamp,
    )

    assert receipt.attempt_count == 2
    assert receipt.base_checkpoint_id == "base"
    assert receipt.base_state_sha256 == "b" * 64


def test_command_base_state_round_trip_is_hash_verified() -> None:
    state = create_initial_state(
        session_id="00000000-0000-4000-8000-000000000001",
        script_id="minimal-case",
        player_id="anonymous",
        player_character_id="player",
    )
    state["answer_key"] = {"culprit": "private"}
    digest = game_state_sha256(state)
    payload = canonical_game_state_payload(state)

    restored = game_state_from_payload(payload, digest)

    assert restored == state
    assert restored["answer_key"] == {"culprit": "private"}


def test_command_base_state_rejects_digest_mismatch() -> None:
    state = create_initial_state(
        session_id="00000000-0000-4000-8000-000000000001",
        script_id="minimal-case",
        player_id="anonymous",
        player_character_id="player",
    )

    try:
        game_state_from_payload(canonical_game_state_payload(state), "0" * 64)
    except ValueError as exc:
        assert "hash mismatch" in str(exc)
    else:
        raise AssertionError("digest mismatch must fail closed")
