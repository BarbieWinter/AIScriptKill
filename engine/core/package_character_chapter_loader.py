"""从剧本包加载角色专属 Markdown 章节。"""

from pathlib import PurePosixPath
from zipfile import ZipFile

import engine.core.package_archive as archive_limits
from engine.core.package_archive import (
    PackageArchiveError,
    parse_yaml_mapping,
)
from engine.core.package_character_chapter_yaml import CharacterChapterFrontmatter
from engine.core.package_schema import CharacterChapterRecord


def load_character_chapters(
    archive: ZipFile,
    names: tuple[str, ...],
    root: str,
) -> tuple[CharacterChapterRecord, ...]:
    """加载可选的 character_scripts/<character>/<chapter>.md 文件。"""

    prefix = f"{root}character_scripts/"
    records: list[CharacterChapterRecord] = []
    for path in sorted(name for name in names if name.startswith(prefix)):
        relative_path = path.removeprefix(root)
        parts = PurePosixPath(relative_path).parts
        if (
            len(parts) != 3
            or parts[0] != "character_scripts"
            or PurePosixPath(parts[2]).suffix != ".md"
            or parts[2] == ".md"
            or PurePosixPath(parts[2]).stem == ""
        ):
            raise PackageArchiveError(
                "PACKAGE_CHARACTER_CHAPTER_PATH_UNSUPPORTED",
                f"人物章节只接受 character_scripts/<character-id>/<chapter-id>.md: {relative_path}",
            )
        frontmatter, content = _read_chapter(archive, path)
        chapter_path_id = PurePosixPath(parts[2]).stem
        if frontmatter.character_id != parts[1] or frontmatter.chapter_id != chapter_path_id:
            raise PackageArchiveError(
                "PACKAGE_CHARACTER_CHAPTER_PATH_INVALID",
                f"人物章节路径与 frontmatter ID 不一致: {relative_path}",
            )
        records.append(
            CharacterChapterRecord(
                id=frontmatter.chapter_id,
                character_id=frontmatter.character_id,
                sort_order=frontmatter.order,
                title=frontmatter.title,
                visibility=frontmatter.visibility,
                release=frontmatter.release.model_dump(mode="json"),
                stage_min=frontmatter.stage_min,
                content=content,
            ),
        )
    return tuple(records)


def _read_chapter(
    archive: ZipFile,
    path: str,
) -> tuple[CharacterChapterFrontmatter, str]:
    with archive.open(path) as member:
        raw_bytes = member.read(archive_limits.MAX_PACKAGE_CHARACTER_CHAPTER_BYTES + 1)
    if len(raw_bytes) > archive_limits.MAX_PACKAGE_CHARACTER_CHAPTER_BYTES:
        raise PackageArchiveError(
            "PACKAGE_CHARACTER_CHAPTER_TOO_LARGE",
            f"{path} 超过人物章节单文件大小上限",
        )
    try:
        raw = raw_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise PackageArchiveError(
            "PACKAGE_CHARACTER_CHAPTER_ENCODING_INVALID",
            f"{path} 必须使用 UTF-8 编码",
        ) from exc

    lines = raw.splitlines(keepends=True)
    if len(lines) == 0 or lines[0].rstrip("\r\n") != "---":
        raise PackageArchiveError(
            "PACKAGE_CHARACTER_CHAPTER_FRONTMATTER_INVALID",
            f"{path} 必须以独占一行的 --- 开始 frontmatter",
        )
    closing_index = next(
        (index for index, line in enumerate(lines[1:], start=1) if line.rstrip("\r\n") == "---"),
        None,
    )
    if closing_index is None:
        raise PackageArchiveError(
            "PACKAGE_CHARACTER_CHAPTER_FRONTMATTER_INVALID",
            f"{path} 缺少 frontmatter 结束分隔符",
        )

    frontmatter_raw = "".join(lines[1:closing_index])
    if frontmatter_raw.strip() == "":
        raise PackageArchiveError(
            "PACKAGE_CHARACTER_CHAPTER_FRONTMATTER_INVALID",
            f"{path} 的 frontmatter 不能为空",
        )
    content = "".join(lines[closing_index + 1 :])
    if content.strip() == "":
        raise PackageArchiveError(
            "PACKAGE_CHARACTER_CHAPTER_BODY_REQUIRED",
            f"{path} 必须包含非空 Markdown 正文",
        )

    frontmatter = CharacterChapterFrontmatter.model_validate(
        parse_yaml_mapping(frontmatter_raw, f"{path} frontmatter"),
    )
    return frontmatter, content
