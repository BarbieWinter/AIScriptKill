from fastapi.testclient import TestClient

from engine.api.main import create_app
from engine.api.middleware.auth import CurrentUser, get_current_user


def test_package_import_requires_login() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/api/v1/packages",
        files={"file": ("package.zip", b"invalid zip", "application/zip")},
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_REQUIRED"


def test_package_import_rejects_non_admin_user() -> None:
    app = create_app()
    app.dependency_overrides[get_current_user] = _authenticated_player
    client = TestClient(app)

    response = client.post(
        "/api/v1/packages",
        files={"file": ("package.zip", b"invalid zip", "application/zip")},
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "ADMIN_REQUIRED"


def test_package_status_update_rejects_non_admin_user() -> None:
    app = create_app()
    app.dependency_overrides[get_current_user] = _authenticated_player
    client = TestClient(app)

    response = client.patch(
        "/api/v1/packages/script-package",
        json={"status": "published"},
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "ADMIN_REQUIRED"


async def _authenticated_player() -> CurrentUser:
    return CurrentUser(subject="00000000-0000-0000-0000-000000000001", role="authenticated")
