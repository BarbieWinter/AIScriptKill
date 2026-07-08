from typing import Protocol, TypeAlias

from sqlalchemy.engine import Result
from sqlalchemy.sql import Executable

DatabaseExecuteResult: TypeAlias = Result[tuple[str, ...]] | None


class WriteSession(Protocol):
    async def execute(self, statement: Executable) -> DatabaseExecuteResult: ...

    async def commit(self) -> None: ...
