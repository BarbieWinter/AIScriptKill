"""为服务层映射器提供严格的标量转换辅助函数。"""

from datetime import datetime
from typing import cast

from sqlalchemy.engine import RowMapping

# ── 显示字段格式化 ──


def timestamp(value: datetime) -> str:
    """将 UTC 日期时间渲染为 API 兼容的 ISO 时间戳。"""

    return value.isoformat().replace("+00:00", "Z")


def definition_value(row: RowMapping, key: str) -> str:
    """从 JSON 定义列读取字符串键，缺失时返回空文本。"""

    definition = row["definition"]
    if not isinstance(definition, dict):
        return ""
    value = cast(dict[str, object], definition).get(key)
    return value if isinstance(value, str) else ""
