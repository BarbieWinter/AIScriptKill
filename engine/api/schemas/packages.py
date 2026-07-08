from typing import Literal, TypeAlias

from pydantic import Field

from engine.api.schemas.common import ApiModel

# ── 剧本包状态类型 ──

PackageStatus: TypeAlias = Literal["draft", "importing", "published", "archived"]


# ── 剧本包校验与导入 ──


class ValidationReport(ApiModel):
    valid: bool = Field(description="Whether package validation passed.")
    warnings: list[str] = Field(description="Validation warnings.")
    errors: list[str] = Field(description="Validation errors.")


class PackageImportResponse(ApiModel):
    package_id: str = Field(description="Script package ID.")
    title: str = Field(description="Script package title.")
    status: PackageStatus = Field(description="Import status.")
    validation: ValidationReport = Field(description="Validation result.")


# ── 发布状态更新 ──


class PackageUpdateRequest(ApiModel):
    status: PackageStatus = Field(description="New package publication status.")


class PackageUpdateResponse(ApiModel):
    package_id: str = Field(description="Script package ID.")
    status: PackageStatus = Field(description="Updated package status.")
    published_at: str = Field(description="Status update timestamp.")


# ── 前端剧本库列表 ──


class PackageSummary(ApiModel):
    id: str = Field(description="Script package ID.")
    title: str = Field(description="Script package title.")
    description: str = Field(description="Script teaser.")
    poster_url: str = Field(description="Poster storage URL.")
    difficulty: int = Field(description="Difficulty from 1 to 5.")
    duration_minutes: int = Field(description="Expected duration.")
    genre: list[str] = Field(description="Genre tags.")
    status: PackageStatus = Field(description="Package status.")
    player_count: int = Field(description="Supported player count.")


class PackageListResponse(ApiModel):
    packages: list[PackageSummary] = Field(description="Visible script packages.")
