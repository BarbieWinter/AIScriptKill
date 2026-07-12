"""定义剧本包导入、发布和目录 API 模型。"""

from typing import Literal, TypeAlias

from pydantic import Field

from engine.api.schemas.common import ApiModel

# ── 剧本包状态类型 ──

PackageStatus: TypeAlias = Literal["draft", "importing", "published", "archived"]


# ── 剧本包校验与导入 ──


class ValidationReport(ApiModel):
    """报告剧本包有效性及面向作者的警告和错误。"""

    valid: bool = Field(description="Whether package validation passed.")
    warnings: list[str] = Field(description="Validation warnings.")
    errors: list[str] = Field(description="Validation errors.")


class PackageImportResponse(ApiModel):
    """返回已导入剧本包的标识和校验结果。"""

    package_id: str = Field(description="Script package ID.")
    title: str = Field(description="Script package title.")
    status: PackageStatus = Field(description="Import status.")
    validation: ValidationReport = Field(description="Validation result.")


# ── 发布状态更新 ──


class PackageUpdateRequest(ApiModel):
    """请求变更剧本包发布状态。"""

    status: PackageStatus = Field(description="New package publication status.")


class PackageUpdateResponse(ApiModel):
    """返回已提交的剧本包发布状态。"""

    package_id: str = Field(description="Script package ID.")
    status: PackageStatus = Field(description="Updated package status.")
    published_at: str = Field(description="Status update timestamp.")


# ── 前端剧本库列表 ──


class PackageSummary(ApiModel):
    """公开剧本包面向玩家且不剧透的目录投影。"""

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
    """返回目录 API 中可见的全部剧本包摘要。"""

    packages: list[PackageSummary] = Field(description="Visible script packages.")
