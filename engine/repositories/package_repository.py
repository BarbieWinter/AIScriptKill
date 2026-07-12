"""持久化已导入剧本包及其规范化内容记录。"""

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


class StoredPackageInfo(BaseModel):
    """存储在 `package.yml.info` 下的面向玩家目录字段。"""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="ignore")

    description: str = Field(default="", description="Player-facing package summary.")
    difficulty: int = Field(default=3, description="Package difficulty from 1 to 5.")
    duration_minutes: int = Field(default=120, description="Estimated play duration in minutes.")
    genre: list[str] = Field(default_factory=list, description="Player-facing genre labels.")
    max_players: int = Field(default=1, description="Maximum supported player count.")


class StoredPackageVisual(BaseModel):
    """存储在 `package.yml.visual` 下的面向玩家目录媒体。"""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="ignore")

    poster: str | None = Field(default=None, description="Opaque package poster locator.")


class StoredPackageConfig(BaseModel):
    """从已存储剧本包清单严格投影目录安全值。"""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="ignore")

    info: StoredPackageInfo = Field(
        default_factory=StoredPackageInfo,
        description="Validated player-facing package information.",
    )
    visual: StoredPackageVisual = Field(
        default_factory=StoredPackageVisual,
        description="Validated player-facing package media.",
    )


@dataclass(frozen=True, slots=True)
class StoredPackage:
    """表示目录查询返回的一个已发布剧本包。"""

    id: str
    name: str
    status: PackageStatus
    config: StoredPackageConfig


@dataclass(frozen=True, slots=True)
class StoredPackageStatus:
    """表示剧本包更新返回的状态字段。"""

    id: str
    status: PackageStatus
    updated_at: datetime


class PackageRepository:
    """读取已发布剧本包并提交显式的剧本包状态变更。"""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def list_published_packages(self) -> list[StoredPackage]:
        """返回按最近更新时间排序的已发布剧本包。"""

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

    async def get_published_package(self, package_id: str) -> StoredPackage | None:
        """按 ID 返回已发布剧本包，不可用时返回 None。"""

        stmt = select(
            script_packages.c.id,
            script_packages.c.name,
            script_packages.c.status,
            script_packages.c.config,
        ).where(
            script_packages.c.id == package_id,
            script_packages.c.status == "published",
        )
        result = await self._db.execute(stmt)
        row = result.mappings().one_or_none()
        if row is None:
            return None
        return stored_package_from_row(row)

    async def update_package_status(
        self,
        package_id: str,
        status: PackageStatus,
    ) -> StoredPackageStatus | None:
        """提交状态更新并返回变更字段，目标缺失时返回 None。"""

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
    """将一条目录查询行映射为类型化的已存储剧本包。"""

    return StoredPackage(
        id=str(row["id"]),
        name=str(row["name"]),
        status=package_status(row),
        config=stored_package_config(row),
    )


def stored_package_config(row: RowMapping) -> StoredPackageConfig:
    """校验已存储 JSON 配置，格式错误时使用空目录默认值。"""

    raw_config = row["config"]
    if not isinstance(raw_config, Mapping):
        return StoredPackageConfig()
    return StoredPackageConfig.model_validate(raw_config)


def stored_package_status_from_row(row: RowMapping) -> StoredPackageStatus:
    """将一条更新返回行映射为类型化剧本包状态。"""

    return StoredPackageStatus(
        id=str(row["id"]),
        status=package_status(row),
        updated_at=row["updated_at"],
    )


def package_status(row: RowMapping) -> PackageStatus:
    """根据公开状态字面量校验数据库状态值。"""

    return PACKAGE_STATUS_ADAPTER.validate_python(row["status"])
