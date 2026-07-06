from collections.abc import Mapping
from datetime import datetime

from sqlalchemy.engine import RowMapping

# ── 显示字段格式化 ──


def timestamp(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def definition_value(row: RowMapping, key: str) -> str:
    definition = row["definition"]
    if not isinstance(definition, Mapping):
        return ""
    value = definition.get(key)
    return value if isinstance(value, str) else ""
