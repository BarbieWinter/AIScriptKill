from dataclasses import dataclass
from pathlib import PurePosixPath
from zipfile import ZipFile

import yaml

from engine.api.schemas.common import JsonValue
from engine.core.package_schema import JsonMapping

# ── ZIP 包错误 ──


@dataclass(frozen=True, slots=True)
class PackageArchiveError(Exception):
    code: str
    message: str

    def __str__(self) -> str:
        return self.message


# ── YAML 读取与 JSONB 归一化 ──


def read_yaml_mapping(archive: ZipFile, path: str) -> JsonMapping:
    raw = archive.read(path).decode("utf-8")
    loaded = yaml.safe_load(raw) or {}
    return json_mapping(loaded, path)


def json_mapping(value, path: str) -> JsonMapping:
    if not isinstance(value, dict):
        raise PackageArchiveError("INVALID_YAML_OBJECT", f"{path} 必须是 YAML object")
    return {str(key): json_value(item) for key, item in value.items()}


def json_value(value) -> JsonValue:
    if value is None or isinstance(value, str | bool | int | float):
        return value
    if isinstance(value, list):
        return [json_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): json_value(item) for key, item in value.items()}
    return str(value)


# ── ZIP 路径定位 ──


def package_path(names: tuple[str, ...]) -> str:
    candidates = tuple(name for name in names if PurePosixPath(name).name == "package.yml")
    if len(candidates) != 1:
        raise PackageArchiveError("PACKAGE_MANIFEST_REQUIRED", "剧本包必须包含唯一的 package.yml")
    return candidates[0]


def yaml_paths(names: tuple[str, ...], root: str, directory: str) -> tuple[str, ...]:
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
    path = PurePosixPath(name)
    return not name.endswith("/") and "__MACOSX" not in path.parts and not path.name.startswith(".")
