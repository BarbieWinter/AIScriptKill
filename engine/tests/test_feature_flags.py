from typing import Any, cast

import pytest

from engine.api.config import Settings

FEATURE_FLAGS = (
    ("MULTIPLAYER_V1", "multiplayer_v1"),
    ("ROOM_EVENTS_V1", "room_events_v1"),
    ("AI_DM_V1", "ai_dm_v1"),
)


def test_multiplayer_feature_flags_default_to_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for env_name, _ in FEATURE_FLAGS:
        monkeypatch.delenv(env_name, raising=False)

    settings = Settings(**cast(dict[str, Any], {"_env_file": None}))

    assert settings.multiplayer_v1 is False
    assert settings.room_events_v1 is False
    assert settings.ai_dm_v1 is False


@pytest.mark.parametrize(("enabled_env", "enabled_field"), FEATURE_FLAGS)
def test_multiplayer_feature_flag_environment_aliases_are_independent(
    monkeypatch: pytest.MonkeyPatch,
    enabled_env: str,
    enabled_field: str,
) -> None:
    for env_name, _ in FEATURE_FLAGS:
        monkeypatch.delenv(env_name, raising=False)
    monkeypatch.setenv(enabled_env, "true")

    settings = Settings(**cast(dict[str, Any], {"_env_file": None}))

    assert {field_name: getattr(settings, field_name) for _, field_name in FEATURE_FLAGS} == {
        field_name: field_name == enabled_field for _, field_name in FEATURE_FLAGS
    }
