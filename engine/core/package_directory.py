"""将松散剧本包目录安全转换为归档导入格式。"""

import os
import stat
from collections.abc import Buffer
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path, PurePosixPath
from typing import IO
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

import engine.core.package_archive as archive_limits
from engine.core.package_archive import PackageArchiveError, visible_file


@dataclass(frozen=True, slots=True)
class _DirectoryMember:
    path: Path
    archive_name: str
    stat_result: os.stat_result


class _BoundedBytesIO(BytesIO):
    def __init__(self, limit: int) -> None:
        super().__init__()
        self._limit = limit
        self._size = 0

    def write(self, data: Buffer, /) -> int:
        planned_size = max(self._size, self.tell() + memoryview(data).nbytes)
        if planned_size > self._limit:
            raise PackageArchiveError(
                "PACKAGE_ARCHIVE_COMPRESSED_TOO_LARGE",
                f"剧本包压缩数据不能超过 {self._limit} 字节",
            )
        written = super().write(data)
        self._size = max(self._size, self.tell())
        return written


def package_directory_archive(package_dir: Path) -> bytes:
    """从非符号链接目录下的普通文件构建受限 ZIP。

    Args:
        package_dir: 包含 `package.yml` 的本地剧本包根目录。

    Returns:
        共享剧本包加载器可接受的 ZIP 字节。

    Raises:
        PackageArchiveError: 根目录或成员不安全、读取期间发生变化，或超出归档资源预算。
    """
    try:
        root_stat = package_dir.lstat()
    except FileNotFoundError as exc:
        raise PackageArchiveError(
            "PACKAGE_DIRECTORY_REQUIRED",
            f"剧本包目录不存在或不是目录: {package_dir}",
        ) from exc
    if stat.S_ISLNK(root_stat.st_mode):
        raise PackageArchiveError(
            "PACKAGE_DIRECTORY_SYMLINK_UNSUPPORTED",
            f"剧本包根目录不允许符号链接: {package_dir}",
        )
    if not stat.S_ISDIR(root_stat.st_mode):
        raise PackageArchiveError(
            "PACKAGE_DIRECTORY_REQUIRED",
            f"剧本包目录不存在或不是目录: {package_dir}",
        )

    members = _directory_members(package_dir)
    buffer = _BoundedBytesIO(archive_limits.MAX_PACKAGE_UPLOAD_BYTES)
    with ZipFile(buffer, "w", compression=ZIP_DEFLATED) as archive:
        for member in members:
            _write_member(archive, member)
    return buffer.getvalue()


def _directory_members(package_dir: Path) -> tuple[_DirectoryMember, ...]:
    root = package_dir.resolve(strict=True)
    members: list[_DirectoryMember] = []
    expanded_bytes = 0
    for path in sorted(package_dir.rglob("*")):
        path_stat = path.lstat()
        archive_name = path.relative_to(package_dir).as_posix()
        if stat.S_ISLNK(path_stat.st_mode):
            raise PackageArchiveError(
                "PACKAGE_DIRECTORY_SYMLINK_UNSUPPORTED",
                f"剧本包不允许符号链接: {archive_name}",
            )
        if stat.S_ISDIR(path_stat.st_mode):
            continue
        if not stat.S_ISREG(path_stat.st_mode):
            raise PackageArchiveError(
                "PACKAGE_DIRECTORY_MEMBER_TYPE_UNSUPPORTED",
                f"剧本包只允许普通文件和目录: {archive_name}",
            )
        if not path.resolve(strict=True).is_relative_to(root):
            raise PackageArchiveError(
                "PACKAGE_DIRECTORY_PATH_UNSAFE",
                f"剧本包文件越过根目录: {archive_name}",
            )
        if not _visible_package_file(archive_name):
            continue
        if len(members) >= archive_limits.MAX_PACKAGE_ARCHIVE_FILES:
            raise PackageArchiveError(
                "PACKAGE_ARCHIVE_FILE_LIMIT_EXCEEDED",
                f"剧本包文件数量不能超过 {archive_limits.MAX_PACKAGE_ARCHIVE_FILES}",
            )
        if path_stat.st_size > archive_limits.MAX_PACKAGE_MEMBER_BYTES:
            raise PackageArchiveError(
                "PACKAGE_ARCHIVE_MEMBER_TOO_LARGE",
                f"剧本包文件解压后过大: {archive_name}",
            )
        expanded_bytes += path_stat.st_size
        if expanded_bytes > archive_limits.MAX_PACKAGE_EXPANDED_BYTES:
            raise PackageArchiveError(
                "PACKAGE_ARCHIVE_EXPANDED_TOO_LARGE",
                "剧本包解压后的总大小超过安全上限",
            )
        members.append(_DirectoryMember(path, archive_name, path_stat))
    return tuple(members)


def _write_member(archive: ZipFile, member: _DirectoryMember) -> None:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        file_descriptor = os.open(member.path, flags)
    except OSError as exc:
        raise PackageArchiveError(
            "PACKAGE_DIRECTORY_FILE_CHANGED",
            f"剧本包文件在导入时发生变化: {member.archive_name}",
        ) from exc
    try:
        opened_stat = os.fstat(file_descriptor)
        if (
            not stat.S_ISREG(opened_stat.st_mode)
            or opened_stat.st_dev != member.stat_result.st_dev
            or opened_stat.st_ino != member.stat_result.st_ino
        ):
            raise PackageArchiveError(
                "PACKAGE_DIRECTORY_FILE_CHANGED",
                f"剧本包文件在导入时发生变化: {member.archive_name}",
            )
        info = ZipInfo(member.archive_name)
        info.create_system = 3
        info.external_attr = (stat.S_IFREG | (opened_stat.st_mode & 0o777)) << 16
        info.compress_type = ZIP_DEFLATED
        with os.fdopen(file_descriptor, "rb", closefd=False) as source:
            with archive.open(info, "w") as destination:
                _copy_exact_member(source, destination, member)
    finally:
        os.close(file_descriptor)


def _copy_exact_member(
    source: IO[bytes],
    destination: IO[bytes],
    member: _DirectoryMember,
) -> None:
    copied = 0
    while chunk := source.read(1024 * 1024):
        copied += len(chunk)
        if copied > member.stat_result.st_size:
            raise PackageArchiveError(
                "PACKAGE_DIRECTORY_FILE_CHANGED",
                f"剧本包文件在导入时发生变化: {member.archive_name}",
            )
        _ = destination.write(chunk)
    if copied != member.stat_result.st_size:
        raise PackageArchiveError(
            "PACKAGE_DIRECTORY_FILE_CHANGED",
            f"剧本包文件在导入时发生变化: {member.archive_name}",
        )


def _visible_package_file(name: str) -> bool:
    path = PurePosixPath(name)
    return visible_file(name) and all(not part.startswith(".") for part in path.parts)
