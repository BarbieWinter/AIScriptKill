from collections.abc import AsyncGenerator
from typing import cast

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from engine.api.errors import ErrorEnvelope
from engine.api.main import create_app
from engine.db.session import get_db_session

VALID_SESSION_ID = "12345678-1234-5678-1234-567812345678"
RESTORE_PAYLOAD = {"action": "restore", "checkpoint_id": "checkpoint-1"}


class _DatabaseAccessForbidden:
    def __getattr__(self, name: str) -> object:
        raise AssertionError(f"restore attempted database access through {name}")


async def _database_access_forbidden() -> AsyncGenerator[AsyncSession]:
    yield cast(AsyncSession, cast(object, _DatabaseAccessForbidden()))


def _app_without_database_access() -> FastAPI:
    app = create_app()
    app.dependency_overrides[get_db_session] = _database_access_forbidden
    return app


def test_restore_rejects_valid_session_id_without_database_access() -> None:
    client = TestClient(_app_without_database_access())

    response = client.patch(
        f"/api/v1/sessions/{VALID_SESSION_ID}",
        json=RESTORE_PAYLOAD,
    )
    detail = ErrorEnvelope.model_validate_json(response.content).error

    assert response.status_code == 409
    assert detail.code == "SESSION_RESTORE_UNAVAILABLE"


def test_restore_preserves_invalid_session_id_error_without_database_access() -> None:
    client = TestClient(_app_without_database_access())

    response = client.patch(
        "/api/v1/sessions/not-a-uuid",
        json=RESTORE_PAYLOAD,
    )
    detail = ErrorEnvelope.model_validate_json(response.content).error

    assert response.status_code == 400
    assert detail.code == "INVALID_SESSION_ID"
