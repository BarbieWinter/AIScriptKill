from engine.api.schemas import (
    PackageImportResponse,
    PackageListResponse,
    PackageUpdateRequest,
    PackageUpdateResponse,
)
from engine.api.schemas.packages import PackageSummary, ValidationReport

# ── 剧本包导入桩 ──


def import_package_stub(filename: str, publish: bool) -> PackageImportResponse:
    status = "published" if publish else "draft"
    return PackageImportResponse(
        package_id="snow-village",
        title=filename.removesuffix(".zip") or "snow-village",
        status=status,
        validation=ValidationReport(valid=True, warnings=[], errors=[]),
    )


# ── 剧本包发布状态桩 ──


def update_package_stub(
    package_id: str,
    payload: PackageUpdateRequest,
) -> PackageUpdateResponse:
    return PackageUpdateResponse(
        package_id=package_id,
        status=payload.status,
        published_at="2026-07-05T12:30:00Z",
    )


# ── 剧本库列表桩 ──


def list_packages_stub() -> PackageListResponse:
    return PackageListResponse(
        packages=[
            PackageSummary(
                id="snow-village",
                title="雪乡连环杀人事件",
                description="暴雪封村后，玩家在熟人社会里追查连环命案真相。",
                poster_url="/storage/packages/snow-village/poster.jpg",
                difficulty=4,
                duration_minutes=120,
                genre=["悬疑", "推理", "沉浸"],
                status="published",
                player_count=6,
            ),
        ],
    )
