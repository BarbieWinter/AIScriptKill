"""定义类型化检查点行、筛选条件和仓储协议。"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol
from uuid import UUID

from langchain_core.runnables import RunnableConfig
from sqlalchemy.sql import Executable


@dataclass(frozen=True, slots=True)
class CheckpointLocator:
    """标识检查点线程、精确检查点和可选命令尝试谱系。"""

    thread_id: str
    checkpoint_id: str | None
    command_id: str | None = None
    command_attempt: int | None = None


@dataclass(frozen=True, slots=True)
class CommandCheckpointContext:
    """绑定一次可续租、可围栏的命令检查点执行。"""

    command_id: UUID
    command_attempt: int
    lease_seconds: int = 30

    def __post_init__(self) -> None:
        if type(self.command_attempt) is not int or self.command_attempt <= 0:
            raise ValueError("command_attempt must be a positive integer")
        if type(self.lease_seconds) is not int or self.lease_seconds <= 0:
            raise ValueError("lease_seconds must be a positive integer")


class AsyncCheckpointOnlyError(Exception):
    """报告在纯异步保存器上使用了同步 API。"""

    def __init__(self, method: str) -> None:
        super().__init__(method)
        self.method = method

    def __str__(self) -> str:
        return f"SupabaseSessionCheckpointSaver.{self.method} requires async LangGraph execution"


class CheckpointConfigError(Exception):
    """报告缺少或无效的 LangGraph 可配置值。"""

    def __init__(self, field: str) -> None:
        super().__init__(field)
        self.field = field

    def __str__(self) -> str:
        return f"LangGraph checkpoint config missing {self.field}"


class CheckpointAttemptFencedError(Exception):
    """报告命令尝试已不再拥有 processing receipt，禁止继续写入。"""

    def __init__(self, thread_id: str, command_id: str, command_attempt: int) -> None:
        super().__init__(thread_id, command_id, command_attempt)
        self.thread_id = thread_id
        self.command_id = command_id
        self.command_attempt = command_attempt

    def __str__(self) -> str:
        return (
            "checkpoint write fenced for command "
            f"{self.command_id} attempt {self.command_attempt} in session {self.thread_id}"
        )


def checkpoint_locator(config: RunnableConfig) -> CheckpointLocator:
    """从可运行配置中提取并校验检查点标识和命令尝试谱系。"""

    configurable = config.get("configurable", {})
    thread_id = configurable.get("thread_id")
    checkpoint_id = configurable.get("checkpoint_id")
    command_id = configurable.get("command_id")
    command_attempt = configurable.get("command_attempt")
    if not isinstance(thread_id, str) or thread_id == "":
        raise CheckpointConfigError("thread_id")
    if command_id is None and command_attempt is not None:
        raise CheckpointConfigError("command_id")
    if command_id is not None:
        if not isinstance(command_id, str) or command_id == "":
            raise CheckpointConfigError("command_id")
        try:
            normalized_command_id = str(UUID(command_id))
        except ValueError as exc:
            raise CheckpointConfigError("command_id") from exc
        if type(command_attempt) is not int or command_attempt <= 0:
            raise CheckpointConfigError("command_attempt")
    else:
        normalized_command_id = None
    return CheckpointLocator(
        thread_id=thread_id,
        checkpoint_id=checkpoint_id if isinstance(checkpoint_id, str) else None,
        command_id=normalized_command_id,
        command_attempt=command_attempt if type(command_attempt) is int else None,
    )


def checkpoint_config(
    thread_id: str,
    checkpoint_id: str | None = None,
    *,
    command_id: UUID | str | None = None,
    command_attempt: int | None = None,
) -> RunnableConfig:
    """为线程、精确检查点或命令尝试谱系构建可运行配置。"""

    configurable: dict[str, str | int] = {"thread_id": thread_id}
    if checkpoint_id is not None and checkpoint_id != "":
        configurable["checkpoint_id"] = checkpoint_id
    if command_id is not None:
        configurable["command_id"] = str(command_id)
    if command_attempt is not None:
        configurable["command_attempt"] = command_attempt
    config: RunnableConfig = {"configurable": configurable}
    _ = checkpoint_locator(config)
    return config


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
