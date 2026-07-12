"""定义类型化检查点行、筛选条件和仓储协议。"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from langchain_core.runnables import RunnableConfig
from sqlalchemy.sql import Executable


@dataclass(frozen=True, slots=True)
class CheckpointLocator:
    """标识检查点线程和可选的精确检查点。"""

    thread_id: str
    checkpoint_id: str | None


class AsyncCheckpointOnlyError(Exception):
    """报告在纯异步保存器上使用了同步 API。"""

    def __init__(self, method: str) -> None:
        super().__init__(method)
        self.method = method

    def __str__(self) -> str:
        return f"SupabaseSessionCheckpointSaver.{self.method} requires async LangGraph execution"


class CheckpointConfigError(Exception):
    """报告缺少必需的 LangGraph 可配置值。"""

    def __init__(self, field: str) -> None:
        super().__init__(field)
        self.field = field

    def __str__(self) -> str:
        return f"LangGraph checkpoint config missing {self.field}"


def checkpoint_locator(config: RunnableConfig) -> CheckpointLocator:
    """从可运行配置中提取并校验检查点标识。"""

    configurable = config.get("configurable", {})
    thread_id = configurable.get("thread_id")
    checkpoint_id = configurable.get("checkpoint_id")
    if not isinstance(thread_id, str) or thread_id == "":
        raise CheckpointConfigError("thread_id")
    return CheckpointLocator(
        thread_id=thread_id,
        checkpoint_id=checkpoint_id if isinstance(checkpoint_id, str) else None,
    )


def checkpoint_config(thread_id: str, checkpoint_id: str | None = None) -> RunnableConfig:
    """为线程或检查点构建 LangGraph 可运行配置。"""

    configurable: dict[str, str] = {"thread_id": thread_id}
    if checkpoint_id is not None and checkpoint_id != "":
        configurable["checkpoint_id"] = checkpoint_id
    return {"configurable": configurable}


class CheckpointDbSession(Protocol):
    """描述检查点保存器所需的事务操作。"""

    async def execute(self, statement: Executable) -> "CheckpointExecuteResult":
        """执行一条类型化 SQL 语句并返回其行适配器。"""
        ...

    async def commit(self) -> None:
        """提交当前事务中的全部检查点变更。"""
        ...

    async def rollback(self) -> None:
        """回滚当前事务中的全部检查点变更。"""
        ...


class CheckpointExecuteResult(Protocol):
    """描述从 SQL 结果到映射行的转换。"""

    def mappings(self) -> "CheckpointRows":
        """返回面向映射的结果行访问接口。"""
        ...


class CheckpointRows(Protocol):
    """描述检查点查询使用的行访问模式。"""

    def one_or_none(self) -> Mapping[str, Any] | None:
        """返回唯一行或无结果，并在上游拒绝多行结果。"""
        ...

    def all(self) -> Sequence[Mapping[str, Any]]:
        """按数据库顺序返回全部结果行。"""
        ...
