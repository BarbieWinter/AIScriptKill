"""提供可注入的 UTC 时钟，以实现确定性引擎行为。"""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Final, Protocol


class Clock(Protocol):
    """向引擎节点提供带时区偏移的当前时间戳。"""

    def now(self) -> str:
        """以带时区偏移的 ISO 时间戳返回当前时间。"""
        ...


@dataclass(frozen=True, slots=True)
class SystemClock:
    """读取当前 UTC 墙上时钟。"""

    def now(self) -> str:
        """以带时区偏移的 ISO 时间戳返回当前 UTC 时间。"""

        return datetime.now(UTC).isoformat()


SYSTEM_CLOCK: Final[Clock] = SystemClock()
