from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from engine.api.errors import ApiError
from engine.api.schemas.packages import PackageUpdateRequest
from engine.core.package_loader import load_package_directory
from engine.repositories.package_repository import StoredPackageStatus
from engine.services import package_service

PACKAGE_ROOT = Path(__file__).resolve().parents[2] / "script-packages" / "mp1-two-player"
LEGACY_PACKAGE_ROOT = Path(__file__).resolve().parents[2] / "script-packages" / "snow-village"


class _StatusRepository:
    def __init__(self) -> None:
        self.update_calls = 0

    async def update_package_status(self, _package_id, _status):
        self.update_calls += 1
        raise AssertionError("invalid package must be rejected before publication")


class _PublishingRepository:
    def __init__(self) -> None:
        self.update_calls = 0

    async def update_package_status(self, package_id, status):
        self.update_calls += 1
        return StoredPackageStatus(
            id=package_id,
            status=status,
            updated_at=datetime(2026, 7, 27, tzinfo=UTC),
        )


def _package_with_missing_ending_mapping():
    package = load_package_directory(PACKAGE_ROOT, publish=False)
    final_stage = package.stages[-1]
    definition = dict(final_stage.definition)
    settlement = dict(definition["settlement"])
    ending_by_outcome = dict(settlement["ending_by_outcome"])
    ending_by_outcome.pop("insufficient-evidence")
    settlement["ending_by_outcome"] = ending_by_outcome
    definition["settlement"] = settlement
    return replace(
        package,
        stages=(*package.stages[:-1], replace(final_stage, definition=definition)),
    )


@pytest.mark.asyncio
async def test_publish_rejects_package_before_status_write_with_playability_diagnostic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    package = _package_with_missing_ending_mapping()
    repository = _StatusRepository()
    db = object()
    get_package = AsyncMock(return_value=package)
    monkeypatch.setattr(package_service, "PackageRepository", lambda _db: repository)
    monkeypatch.setattr(package_service, "get_runtime_package", get_package)

    with pytest.raises(ApiError) as exc_info:
        await package_service.update_package(
            package.package.id,
            PackageUpdateRequest(status="published"),
            db,  # type: ignore[arg-type]
        )

    assert exc_info.value.error.code == "PACKAGE_NOT_MULTIPLAYER"
    assert exc_info.value.error.message == ("最终判断结果缺少结局映射: insufficient-evidence")
    assert exc_info.value.error.details["diagnostic_code"] == (
        "PACKAGE_MULTIPLAYER_ENDING_MAPPING_MISSING"
    )
    assert exc_info.value.error.details["stage_id"] == "final-judgment"
    assert exc_info.value.error.details["outcome_id"] == "insufficient-evidence"
    get_package.assert_awaited_once_with(
        db,
        package.package.id,
        for_update=True,
        published_only=False,
    )
    assert repository.update_calls == 0


@pytest.mark.asyncio
async def test_publish_allows_version_without_multiplayer_policy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    package = load_package_directory(LEGACY_PACKAGE_ROOT, publish=False)
    repository = _PublishingRepository()
    db = object()
    get_package = AsyncMock(return_value=package)
    monkeypatch.setattr(package_service, "PackageRepository", lambda _db: repository)
    monkeypatch.setattr(package_service, "get_runtime_package", get_package)

    response = await package_service.update_package(
        package.package.id,
        PackageUpdateRequest(status="published"),
        db,  # type: ignore[arg-type]
    )

    assert response.package_id == package.package.id
    assert response.status == "published"
    assert repository.update_calls == 1
