from uuid import UUID, uuid4

import pytest
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import ValidationError

from engine.api.errors import ApiError
from engine.api.middleware import auth
from engine.api.middleware.auth import (
    SupabaseClaims,
    VerifiedAnonymousPrincipal,
    get_verified_anonymous_principal,
    require_verified_anonymous_principal,
)
from engine.api.schemas.multiplayer_rooms import (
    CreateMultiplayerSessionRequest,
    LobbySnapshotV1,
    UpdateScenePresenceRequest,
)
from engine.contracts.multiplayer_v1.commands import (
    AssignCharacterCommand,
    SendDiscussionMessagePayload,
)
from engine.services.multiplayer_feature import require_multiplayer_enabled


class _Verifier:
    def __init__(self, claims: SupabaseClaims) -> None:
        self.claims = claims

    def verify(self, _: str) -> SupabaseClaims:
        return self.claims


def _credentials() -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials="token")


def _claims(*, subject: str | None = None, anonymous: bool = True) -> SupabaseClaims:
    return SupabaseClaims(
        sub=subject or str(uuid4()),
        exp=4_000_000_000,
        is_anonymous=anonymous,
    )


@pytest.mark.asyncio
async def test_multiplayer_principal_requires_bearer_token() -> None:
    with pytest.raises(ApiError) as exc_info:
        await get_verified_anonymous_principal(None)

    assert exc_info.value.status_code == 401
    assert exc_info.value.error.code == "AUTH_REQUIRED"


@pytest.mark.asyncio
async def test_multiplayer_principal_accepts_verified_anonymous_uuid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    claims = _claims()
    monkeypatch.setattr(auth, "get_jwt_verifier", lambda: _Verifier(claims))

    principal = await get_verified_anonymous_principal(_credentials())

    assert principal == VerifiedAnonymousPrincipal(id=UUID(claims.sub))


@pytest.mark.asyncio
async def test_multiplayer_principal_can_use_current_user_dependency_override() -> None:
    claims = _claims()
    principal = await require_verified_anonymous_principal(
        auth.CurrentUser(
            subject=claims.sub,
            role="authenticated",
            is_anonymous=True,
        )
    )

    assert principal.id == UUID(claims.sub)


@pytest.mark.asyncio
async def test_multiplayer_principal_rejects_non_anonymous_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(auth, "get_jwt_verifier", lambda: _Verifier(_claims(anonymous=False)))

    with pytest.raises(ApiError) as exc_info:
        await get_verified_anonymous_principal(_credentials())

    assert exc_info.value.status_code == 403
    assert exc_info.value.error.code == "ANONYMOUS_IDENTITY_REQUIRED"


@pytest.mark.asyncio
async def test_multiplayer_principal_rejects_non_uuid_subject(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(auth, "get_jwt_verifier", lambda: _Verifier(_claims(subject="anonymous")))

    with pytest.raises(ApiError) as exc_info:
        await get_verified_anonymous_principal(_credentials())

    assert exc_info.value.status_code == 401
    assert exc_info.value.error.code == "INVALID_USER_ID"


def test_multiplayer_feature_gate_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "engine.services.multiplayer_feature.get_settings",
        lambda: type("Settings", (), {"multiplayer_v1": False})(),
    )

    with pytest.raises(ApiError) as exc_info:
        require_multiplayer_enabled()

    assert exc_info.value.status_code == 503
    assert exc_info.value.error.code == "MULTIPLAYER_DISABLED"


def test_lobby_command_parses_browser_uuid_string() -> None:
    command_id = uuid4()

    command = AssignCharacterCommand.model_validate(
        {
            "command_id": str(command_id),
            "expected_revision": 0,
            "type": "room.assign_character",
            "payload": {"character_id": "investigator"},
        }
    )

    assert command.command_id == command_id


def test_discussion_payload_parses_browser_uuid_string() -> None:
    message_id = uuid4()

    payload = SendDiscussionMessagePayload.model_validate(
        {
            "stage_id": "investigation",
            "message_id": str(message_id),
            "text": "测试消息",
        }
    )

    assert payload.message_id == message_id


def test_multiplayer_create_schema_rejects_actor_spoofing() -> None:
    with pytest.raises(ValidationError):
        CreateMultiplayerSessionRequest.model_validate(
            {
                "mode": "multiplayer_v1",
                "script_id": "mp1-two-player",
                "principal_id": str(uuid4()),
            }
        )


def test_lobby_snapshot_schema_has_no_private_authority_fields() -> None:
    member_id = uuid4()
    snapshot = LobbySnapshotV1.model_validate(
        {
            "session_id": uuid4(),
            "mode": "multiplayer_v1",
            "status": "lobby",
            "revision": 3,
            "package": {
                "script_id": "mp1-two-player",
                "title": "两份口供",
                "version": "1.0.0",
            },
            "capacity": {"min_players": 2, "max_players": 2, "joined": 1},
            "self": {
                "member_id": member_id,
                "room_role": "host",
                "character_id": None,
                "ready": False,
            },
            "members": [
                {
                    "member_id": member_id,
                    "room_role": "host",
                    "character_id": None,
                    "ready": False,
                }
            ],
            "characters": [
                {
                    "id": "investigator",
                    "name": "调查员",
                    "public_description": "负责核对异常记录",
                    "assigned_member_id": None,
                }
            ],
            "capabilities": {
                "can_invite": True,
                "can_assign_character": True,
                "can_ready": False,
                "can_start": False,
            },
            "invites": [],
        }
    )

    serialized = snapshot.model_dump(mode="json")
    assert "principal_id" not in str(serialized)
    assert "runtime_package_snapshot" not in str(serialized)
    assert "chapters" not in str(serialized)


def test_scene_presence_schema_rejects_identity_spoofing_and_invalid_coordinates() -> None:
    valid = {
        "x": 1200,
        "y": 970.5,
        "facing": "left",
        "moving": True,
    }
    parsed = UpdateScenePresenceRequest.model_validate(valid)
    assert parsed.x == 1200
    assert parsed.y == 970.5

    for extra in ("member_id", "principal_id", "character_id", "updated_at", "revision"):
        with pytest.raises(ValidationError):
            UpdateScenePresenceRequest.model_validate({**valid, extra: str(uuid4())})

    for invalid in (
        {**valid, "x": -1},
        {**valid, "x": 2400},
        {**valid, "y": float("inf")},
        {**valid, "x": "1200"},
        {**valid, "facing": "up"},
        {**valid, "moving": 1},
    ):
        with pytest.raises(ValidationError):
            UpdateScenePresenceRequest.model_validate(invalid)
