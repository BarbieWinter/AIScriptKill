"""在路径、数量和大小安全预算内检查剧本包归档。"""

import stat
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from math import isfinite
from pathlib import PurePosixPath
from typing import Final, cast
from zipfile import ZipFile, ZipInfo

import yaml
from yaml.events import AliasEvent, CollectionEndEvent, CollectionStartEvent, Event, NodeEvent
from yaml.nodes import MappingNode, Node, ScalarNode, SequenceNode

from engine.api.schemas.common import JsonValue
from engine.core.package_schema import JsonMapping

MAX_PACKAGE_UPLOAD_BYTES: Final = 64 * 1024 * 1024
MAX_PACKAGE_ARCHIVE_FILES: Final = 2048
MAX_PACKAGE_MEMBER_BYTES: Final = 64 * 1024 * 1024
MAX_PACKAGE_EXPANDED_BYTES: Final = 512 * 1024 * 1024
MAX_PACKAGE_COMPRESSION_RATIO: Final = 200.0
MAX_PACKAGE_YAML_BYTES: Final = 1024 * 1024
MAX_PACKAGE_CHARACTER_CHAPTER_BYTES: Final = 1024 * 1024
MAX_PACKAGE_YAML_DEPTH: Final = 64
MAX_PACKAGE_YAML_NODES: Final = 50_000

# ── ZIP 包错误 ──


# Python 会为抛出的异常写入回溯状态，因此该值不能设为冻结。
@dataclass(slots=True)
class PackageArchiveError(Exception):
    """携带稳定的导入错误码和面向剧本包作者的消息。"""

    code: str
    message: str

    def __str__(self) -> str:
        return self.message


def validate_archive_members(members: tuple[ZipInfo, ...]) -> None:
    """在读取任何成员前拒绝不安全或超出预算的 ZIP 元数据。"""
    if len(members) > MAX_PACKAGE_ARCHIVE_FILES:
        raise PackageArchiveError(
            "PACKAGE_ARCHIVE_FILE_LIMIT_EXCEEDED",
            f"剧本包文件数量不能超过 {MAX_PACKAGE_ARCHIVE_FILES}",
        )

    expanded_bytes = 0
    member_names: set[str] = set()
    for member in members:
        if member.filename in member_names:
            raise PackageArchiveError(
                "PACKAGE_ARCHIVE_DUPLICATE_MEMBER",
                f"剧本包包含重复文件名: {member.filename}",
            )
        member_names.add(member.filename)
        _validate_member_path(member.filename)
        _validate_member_type(member)
        if member.is_dir():
            continue
        if member.file_size > MAX_PACKAGE_MEMBER_BYTES:
            raise PackageArchiveError(
                "PACKAGE_ARCHIVE_MEMBER_TOO_LARGE",
                f"剧本包文件解压后过大: {member.filename}",
            )
        expanded_bytes += member.file_size
        if expanded_bytes > MAX_PACKAGE_EXPANDED_BYTES:
            raise PackageArchiveError(
                "PACKAGE_ARCHIVE_EXPANDED_TOO_LARGE",
                "剧本包解压后的总大小超过安全上限",
            )
        compressed_bytes = max(member.compress_size, 1)
        if member.file_size / compressed_bytes > MAX_PACKAGE_COMPRESSION_RATIO:
            raise PackageArchiveError(
                "PACKAGE_ARCHIVE_COMPRESSION_RATIO_EXCEEDED",
                f"剧本包文件压缩比异常: {member.filename}",
            )


def _validate_member_type(member: ZipInfo) -> None:
    if member.create_system != 3:
        return
    file_type = stat.S_IFMT(member.external_attr >> 16)
    if file_type == stat.S_IFLNK:
        raise PackageArchiveError(
            "PACKAGE_ARCHIVE_SYMLINK_UNSUPPORTED",
            f"剧本包不允许符号链接: {member.filename}",
        )
    expected_type = stat.S_IFDIR if member.is_dir() else stat.S_IFREG
    if file_type not in {0, expected_type}:
        raise PackageArchiveError(
            "PACKAGE_ARCHIVE_MEMBER_TYPE_UNSUPPORTED",
            f"剧本包只允许普通文件和目录: {member.filename}",
        )


def _validate_member_path(name: str) -> None:
    path = PurePosixPath(name)
    # ZIP 成员名采用 POSIX 路径；拒绝其他分隔符可确保所有解压平台遵循相同的遍历约束。
    if (
        name == ""
        or "\\" in name
        or path.is_absolute()
        or ".." in path.parts
        or (len(path.parts) > 0 and path.parts[0].endswith(":"))
    ):
        raise PackageArchiveError(
            "PACKAGE_ARCHIVE_PATH_UNSAFE",
            f"剧本包包含不安全路径: {name}",
        )


# ── YAML 读取与 JSONB 归一化 ──


def read_yaml_mapping(archive: ZipFile, path: str) -> JsonMapping:
    """在预算内读取一个 YAML 文档，并要求根节点为映射。"""

    with archive.open(path) as member:
        raw_bytes = member.read(MAX_PACKAGE_YAML_BYTES + 1)
    if len(raw_bytes) > MAX_PACKAGE_YAML_BYTES:
        raise PackageArchiveError(
            "PACKAGE_YAML_TOO_LARGE",
            f"{path} 超过 YAML 单文件大小上限",
        )
    try:
        raw = raw_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise PackageArchiveError(
            "PACKAGE_YAML_ENCODING_INVALID",
            f"{path} 必须使用 UTF-8 编码",
        ) from exc
    return parse_yaml_mapping(raw, path)


def parse_yaml_mapping(raw: str, path: str) -> JsonMapping:
    """安全解析一段 YAML 文本，并要求根节点为 JSON 兼容映射。"""

    if len(raw.encode("utf-8")) > MAX_PACKAGE_YAML_BYTES:
        raise PackageArchiveError(
            "PACKAGE_YAML_TOO_LARGE",
            f"{path} 超过 YAML 单文件大小上限",
        )
    _validate_yaml_event_budget(raw, path)
    _validate_yaml_unique_keys(raw, path)
    try:
        loaded: object = yaml.safe_load(raw) or {}
    except yaml.YAMLError as exc:
        raise PackageArchiveError(
            "PACKAGE_YAML_SYNTAX_INVALID",
            f"{path} 包含无效 YAML 语法",
        ) from exc
    return json_mapping(loaded, path)


def _validate_yaml_event_budget(raw: str, path: str) -> None:
    depth = 0
    nodes = 0
    try:
        parse_yaml = cast(Callable[..., Iterable[Event]], getattr(yaml, "parse"))
        events = parse_yaml(raw, Loader=yaml.SafeLoader)
        for event in events:
            if isinstance(event, AliasEvent):
                raise PackageArchiveError(
                    "PACKAGE_YAML_ALIAS_UNSUPPORTED",
                    f"{path} 不允许 YAML alias",
                )
            if isinstance(event, NodeEvent):
                nodes += 1
                if nodes > MAX_PACKAGE_YAML_NODES:
                    raise PackageArchiveError(
                        "PACKAGE_YAML_COMPLEXITY_EXCEEDED",
                        f"{path} 的 YAML 节点数量超过安全上限",
                    )
            if isinstance(event, CollectionStartEvent):
                depth += 1
                if depth > MAX_PACKAGE_YAML_DEPTH:
                    raise PackageArchiveError(
                        "PACKAGE_YAML_COMPLEXITY_EXCEEDED",
                        f"{path} 的 YAML 嵌套深度超过安全上限",
                    )
            elif isinstance(event, CollectionEndEvent):
                depth -= 1
    except yaml.YAMLError as exc:
        raise PackageArchiveError(
            "PACKAGE_YAML_SYNTAX_INVALID",
            f"{path} 包含无效 YAML 语法",
        ) from exc


def _validate_yaml_unique_keys(raw: str, path: str) -> None:
    try:
        compose_yaml = cast(Callable[..., Node | None], getattr(yaml, "compose"))
        root = compose_yaml(raw, Loader=yaml.SafeLoader)
    except yaml.YAMLError as exc:
        raise PackageArchiveError(
            "PACKAGE_YAML_SYNTAX_INVALID",
            f"{path} 包含无效 YAML 语法",
        ) from exc
    if root is not None:
        _validate_yaml_node_keys(root, path)


def _validate_yaml_node_keys(node: Node, path: str) -> None:
    if isinstance(node, MappingNode):
        seen: set[tuple[str, str]] = set()
        for key_node, value_node in node.value:
            if isinstance(key_node, ScalarNode):
                key = (key_node.tag, key_node.value)
                if key in seen:
                    raise PackageArchiveError(
                        "PACKAGE_YAML_DUPLICATE_KEY",
                        f"{path} 包含重复 YAML 键: {key_node.value}",
                    )
                seen.add(key)
            _validate_yaml_node_keys(value_node, path)
        return
    if isinstance(node, SequenceNode):
        for item in node.value:
            _validate_yaml_node_keys(item, path)


def json_mapping(value: object, path: str) -> JsonMapping:
    """校验对象是否为指定路径下以字符串为键的 JSON 映射。"""

    if not isinstance(value, dict):
        raise PackageArchiveError("INVALID_YAML_OBJECT", f"{path} 必须是 YAML object")
    mapping = cast(dict[object, object], value)
    return _json_mapping(mapping, path)


def json_value(value: object, path: str) -> JsonValue:
    if value is None or isinstance(value, str | bool | int):
        return value
    if isinstance(value, float):
        if isfinite(value):
            return value
        raise _invalid_yaml_type(path, "非有限浮点数")
    if isinstance(value, list):
        items = cast(list[object], value)
        return [json_value(item, f"{path}[{index}]") for index, item in enumerate(items)]
    if isinstance(value, dict):
        mapping = cast(dict[object, object], value)
        return _json_mapping(mapping, path)
    raise _invalid_yaml_type(path, type(value).__name__)


def _json_mapping(value: dict[object, object], path: str) -> JsonMapping:
    result: JsonMapping = {}
    for key, item in value.items():
        if not isinstance(key, str):
            raise _invalid_yaml_type(path, "非字符串映射键")
        result[key] = json_value(item, f"{path}.{key}")
    return result


def _invalid_yaml_type(path: str, actual: str) -> PackageArchiveError:
    return PackageArchiveError(
        "PACKAGE_YAML_TYPE_INVALID",
        f"{path} 包含非 JSON YAML 类型: {actual}",
    )


# ── ZIP 路径定位 ──


def package_path(names: tuple[str, ...]) -> str:
    """返回唯一的 package.yml 路径，缺失时抛出稳定错误。"""

    candidates = tuple(name for name in names if PurePosixPath(name).name == "package.yml")
    if len(candidates) != 1:
        raise PackageArchiveError("PACKAGE_MANIFEST_REQUIRED", "剧本包必须包含唯一的 package.yml")
    return candidates[0]


def yaml_paths(names: tuple[str, ...], root: str, directory: str) -> tuple[str, ...]:
    """返回剧本包目录直属的可见 YAML 路径。"""

    prefix = f"{root}{directory}/"
    return tuple(
        sorted(
            name
            for name in names
            if name.startswith(prefix)
            and PurePosixPath(name).name != "_index.yml"
            and PurePosixPath(name).suffix in {".yml", ".yaml"}
        ),
    )


def visible_file(name: str) -> bool:
    """返回归档路径是否既非隐藏文件也非元数据文件。"""

    path = PurePosixPath(name)
    return (
        not name.endswith("/")
        and "__MACOSX" not in path.parts
        and all(not part.startswith(".") for part in path.parts)
    )
