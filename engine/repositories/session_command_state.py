"""Canonical encoding and hashing for durable runtime command states."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import cast

from engine.api.schemas.common import JsonValue
from engine.core.game_state import GameState
from engine.core.game_state_codec import game_state_from_mapping
from engine.core.package_archive import json_value


def canonical_game_state_payload(state: GameState) -> dict[str, object]:
    """Return a JSON-safe full-state projection without dropping private fields."""

    return {
        str(key): json_value(value, f"game_state.{key}")
        for key, value in cast(Mapping[object, object], state).items()
    }


def game_state_sha256(state: GameState) -> str:
    """Hash the canonical compact UTF-8 representation of a full GameState."""

    encoded = json.dumps(
        canonical_game_state_payload(state),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def game_state_from_payload(value: object, expected_sha256: str) -> GameState:
    """Strictly decode a stored base state after verifying its canonical digest."""

    if not isinstance(value, dict):
        raise ValueError("stored command base state is not an object")
    raw = cast(Mapping[object, object], value)
    payload: dict[str, JsonValue] = {
        str(key): json_value(item, f"command_base_state.{key}")
        for key, item in raw.items()
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    if hashlib.sha256(encoded).hexdigest() != expected_sha256:
        raise ValueError("stored command base state hash mismatch")
    return game_state_from_mapping(payload)
