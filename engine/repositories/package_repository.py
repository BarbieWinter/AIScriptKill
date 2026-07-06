from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import ClassVar, Final

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter
from sqlalchemy import func, select, update
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncSession

from engine.api.schemas.packages import PackageStatus
from engine.db.tables import script_packages

# ── 剧本包读取 Repository ──

PACKAGE_STATUS_ADAPTER: Final = TypeAdapter[PackageStatus](PackageStatus)


class StoredPackageConfig(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="ignore")

    description: str = Field(default="")
    poster_url: str = Field(default="")
    difficulty: int = Field(default=3)
    duration_minutes: int = Field(default=120)
    genre: list[str] = Field(default_factory=list)
    player_count: int = Field(default=1)


@dataclass(frozen=True, slots=True)
class StoredPackage:
    id: str
    name: str
    status: PackageStatus
    config: StoredPackageConfig


@dataclass(frozen=True, slots=True)
class StoredPackageStatus:
    id: str
    status: PackageStatus
    updated_at: datetime


class PackageRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def list_published_packages(self) -> list[StoredPackage]:
        stmt = (
            select(
                script_packages.c.id,
                script_packages.c.name,
                script_packages.c.status,
                script_packages.c.config,
            )
            .where(script_packages.c.status == "published")
            .order_by(script_packages.c.updated_at.desc())
        )
        result = await self._db.execute(stmt)
        return [stored_package_from_row(row) for row in result.mappings().all()]

    async def update_package_status(
        self,
        package_id: str,
        status: PackageStatus,
    ) -> StoredPackageStatus | None:
        stmt = (
            update(script_packages)
            .where(script_packages.c.id == package_id)
            .values(status=status, updated_at=func.now())
            .returning(
                script_packages.c.id,
                script_packages.c.status,
                script_packages.c.updated_at,
            )
        )
        result = await self._db.execute(stmt)
        row = result.mappings().one_or_none()
        if row is None:
            return None
        await self._db.commit()
        return stored_package_status_from_row(row)


def stored_package_from_row(row: RowMapping) -> StoredPackage:
    return StoredPackage(
        id=str(row["id"]),
        name=str(row["name"]),
        status=package_status(row),
        config=stored_package_config(row),
    )


def stored_package_config(row: RowMapping) -> StoredPackageConfig:
    raw_config = row["config"]
    if not isinstance(raw_config, Mapping):
        return StoredPackageConfig()
    return StoredPackageConfig.model_validate(raw_config)


def stored_package_status_from_row(row: RowMapping) -> StoredPackageStatus:
    return StoredPackageStatus(
        id=str(row["id"]),
        status=package_status(row),
        updated_at=row["updated_at"],
    )


def package_status(row: RowMapping) -> PackageStatus:
    return PACKAGE_STATUS_ADAPTER.validate_python(row["status"])
