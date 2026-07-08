from io import BytesIO
from pathlib import Path, PurePosixPath
from zipfile import ZipFile

from engine.core.package_archive import PackageArchiveError, visible_file


def package_directory_archive(package_dir: Path) -> bytes:
    if not package_dir.is_dir():
        raise PackageArchiveError(
            "PACKAGE_DIRECTORY_REQUIRED",
            f"剧本包目录不存在或不是目录: {package_dir}",
        )

    buffer = BytesIO()
    with ZipFile(buffer, "w") as archive:
        for path in sorted(package_dir.rglob("*")):
            if path.is_file():
                archive_name = path.relative_to(package_dir).as_posix()
                if _visible_package_file(archive_name):
                    archive.write(path, archive_name)
    return buffer.getvalue()


def _visible_package_file(name: str) -> bool:
    path = PurePosixPath(name)
    return visible_file(name) and all(not part.startswith(".") for part in path.parts)
