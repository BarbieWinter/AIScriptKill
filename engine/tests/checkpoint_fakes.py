import asyncio
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, cast
from uuid import UUID

from sqlalchemy.dialects import postgresql
from sqlalchemy.sql import ClauseElement, Executable

from engine.api.schemas.common import JsonValue


@dataclass(frozen=True, slots=True)
class MemoryCheckpointRow:
    session_id: UUID
    thread_ts: str
    parent_ts: str | None
    state: dict[str, JsonValue]
    command_id: UUID | None
    command_attempt: int | None
    sequence: int


@dataclass(frozen=True, slots=True)
class MemoryCheckpointWriteRow:
    session_id: UUID
    checkpoint_id: str
    task_id: str
    write_idx: int
    channel: str
    value: dict[str, JsonValue]
    sequence: int


class MemoryCheckpointSession:
    def __init__(self) -> None:
        self.rows: list[MemoryCheckpointRow] = []
        self.writes: list[MemoryCheckpointWriteRow] = []
        self.commit_count = 0
        self._sequence = 0
        self.active_command_attempts: dict[tuple[UUID, UUID], int] = {}
        self.lease_renewals: list[tuple[UUID, UUID, int, int]] = []

    def activate_command_attempt(
        self,
        session_id: UUID,
        command_id: UUID,
        command_attempt: int,
    ) -> None:
        self.active_command_attempts[(session_id, command_id)] = command_attempt

    async def execute(self, statement: Executable) -> "MemoryCheckpointResult":
        if not isinstance(statement, ClauseElement):
            raise AssertionError("checkpoint fake only accepts SQL clause statements")
        compiled = statement.compile(dialect=postgresql.dialect())
        params = compiled.params or {}
        compiled_sql = compiled.string.upper()
        targets_writes = "SESSION_CHECKPOINT_WRITES" in compiled_sql
        targets_receipts = "SESSION_COMMAND_RECEIPTS" in compiled_sql
        if targets_receipts:
            return MemoryCheckpointResult(self._renew_command_lease(params))
        if getattr(statement, "is_insert", False):
            if targets_writes:
                self._insert_writes(params, update_special="DO UPDATE" in compiled_sql)
            else:
                self._insert(
                    params,
                    is_upsert="ON CONFLICT" in compiled_sql,
                    refresh_order="CREATED_AT =" in compiled_sql,
                )
            return MemoryCheckpointResult([])
        if getattr(statement, "is_update", False):
            self._update(params)
            return MemoryCheckpointResult([])
        if getattr(statement, "is_delete", False):
            if targets_writes:
                self._delete_writes(params)
            else:
                self._delete(params)
            return MemoryCheckpointResult([])
        if targets_writes:
            return MemoryCheckpointResult(self._select_writes(params))
        return MemoryCheckpointResult(
            self._select(
                params,
                order_by_thread_ts="ORDER BY SESSION_CHECKPOINTS.THREAD_TS DESC"
                in compiled.string.upper(),
                command_attempt_at_most="COMMAND_ATTEMPT <=" in compiled.string.upper(),
            )
        )

    async def commit(self) -> None:
        self.commit_count += 1

    async def rollback(self) -> None:
        pass

    def _renew_command_lease(self, params: Mapping[str, Any]) -> list[Mapping[str, Any]]:
        session_id = _uuid_named(params, "session_id")
        command_id = _uuid_named(params, "command_id")
        command_attempt = _int_value(params, "attempt_count")
        active_attempt = self.active_command_attempts.get((session_id, command_id))
        if active_attempt != command_attempt:
            return []
        lease_seconds = next(
            (
                int(value.total_seconds())
                for value in params.values()
                if hasattr(value, "total_seconds")
            ),
            30,
        )
        self.lease_renewals.append((session_id, command_id, command_attempt, lease_seconds))
        return [{"command_id": command_id}]

    def _insert(
        self,
        params: Mapping[str, Any],
        *,
        is_upsert: bool,
        refresh_order: bool,
    ) -> None:
        session_id = _uuid_value(params)
        thread_ts = _string_value(params, "thread_ts")
        parent_ts = params.get("parent_ts")
        state = params.get("state")
        command_id = _optional_uuid_named(params, "command_id")
        command_attempt = _optional_int_value(params, "command_attempt")
        assert isinstance(parent_ts, str) or parent_ts is None
        assert isinstance(state, dict)
        self._sequence += 1
        row = MemoryCheckpointRow(
            session_id=session_id,
            thread_ts=thread_ts,
            parent_ts=parent_ts,
            state=cast(dict[str, JsonValue], state),
            command_id=command_id,
            command_attempt=command_attempt,
            sequence=self._sequence,
        )
        if is_upsert:
            for index, existing in enumerate(self.rows):
                if existing.session_id == session_id and existing.thread_ts == thread_ts:
                    self.rows[index] = MemoryCheckpointRow(
                        session_id=row.session_id,
                        thread_ts=row.thread_ts,
                        parent_ts=row.parent_ts,
                        state=row.state,
                        command_id=row.command_id,
                        command_attempt=row.command_attempt,
                        sequence=row.sequence if refresh_order else existing.sequence,
                    )
                    return
        self.rows.append(row)

    def _insert_writes(self, params: Mapping[str, Any], *, update_special: bool) -> None:
        for values in _insert_parameter_rows(params):
            session_id = _uuid_value(values)
            checkpoint_id = _string_value(values, "checkpoint_id")
            task_id = _string_value(values, "task_id")
            write_idx = _int_value(values, "write_idx")
            channel = _string_value(values, "channel")
            value = values.get("value")
            assert isinstance(value, dict)
            for index, existing in enumerate(self.writes):
                if (
                    existing.session_id == session_id
                    and existing.checkpoint_id == checkpoint_id
                    and existing.task_id == task_id
                    and existing.write_idx == write_idx
                ):
                    if update_special and write_idx < 0:
                        self.writes[index] = MemoryCheckpointWriteRow(
                            session_id=session_id,
                            checkpoint_id=checkpoint_id,
                            task_id=task_id,
                            write_idx=write_idx,
                            channel=channel,
                            value=cast(dict[str, JsonValue], value),
                            sequence=existing.sequence,
                        )
                    break
            else:
                self._sequence += 1
                self.writes.append(
                    MemoryCheckpointWriteRow(
                        session_id=session_id,
                        checkpoint_id=checkpoint_id,
                        task_id=task_id,
                        write_idx=write_idx,
                        channel=channel,
                        value=cast(dict[str, JsonValue], value),
                        sequence=self._sequence,
                    )
                )

    def _update(self, params: Mapping[str, Any]) -> None:
        session_id = _uuid_value(params)
        thread_ts = _string_value(params, "thread_ts")
        state = params.get("state")
        assert isinstance(state, dict)
        for index, existing in enumerate(self.rows):
            if existing.session_id == session_id and existing.thread_ts == thread_ts:
                self.rows[index] = MemoryCheckpointRow(
                    session_id=existing.session_id,
                    thread_ts=existing.thread_ts,
                    parent_ts=existing.parent_ts,
                    state=cast(dict[str, JsonValue], state),
                    command_id=existing.command_id,
                    command_attempt=existing.command_attempt,
                    sequence=existing.sequence,
                )
                return

    def _delete(self, params: Mapping[str, Any]) -> None:
        session_id = _uuid_value(params)
        self.rows = [row for row in self.rows if row.session_id != session_id]

    def _delete_writes(self, params: Mapping[str, Any]) -> None:
        session_id = _uuid_value(params)
        self.writes = [row for row in self.writes if row.session_id != session_id]

    def _select(
        self,
        params: Mapping[str, Any],
        *,
        order_by_thread_ts: bool,
        command_attempt_at_most: bool,
    ) -> list[Mapping[str, Any]]:
        session_id = _uuid_value(params)
        checkpoint_ids = {value for value in params.values() if isinstance(value, str)}
        rows = [row for row in self.rows if row.session_id == session_id]
        matching_ids = checkpoint_ids.intersection(row.thread_ts for row in rows)
        if matching_ids:
            rows = [row for row in rows if row.thread_ts in matching_ids]
        command_id = _optional_uuid_named(params, "command_id")
        command_attempt = _optional_int_value(params, "command_attempt")
        if command_id is not None:
            rows = [row for row in rows if row.command_id == command_id]
        if command_attempt is not None:
            if command_attempt_at_most:
                rows = [
                    row
                    for row in rows
                    if row.command_attempt is not None and row.command_attempt <= command_attempt
                ]
            else:
                rows = [row for row in rows if row.command_attempt == command_attempt]
        if order_by_thread_ts:
            rows.sort(key=lambda row: row.thread_ts, reverse=True)
        else:
            rows.sort(key=lambda row: row.sequence, reverse=True)
        return [
            {
                "session_id": row.session_id,
                "thread_ts": row.thread_ts,
                "parent_ts": row.parent_ts,
                "state": row.state,
                "command_id": row.command_id,
                "command_attempt": row.command_attempt,
            }
            for row in rows
        ]

    def _select_writes(self, params: Mapping[str, Any]) -> list[Mapping[str, Any]]:
        session_id = _uuid_value(params)
        checkpoint_ids = _checkpoint_id_values(params)
        rows = [row for row in self.writes if row.session_id == session_id]
        if checkpoint_ids:
            rows = [row for row in rows if row.checkpoint_id in checkpoint_ids]
        rows.sort(key=lambda row: (row.checkpoint_id, row.task_id, row.write_idx))
        return [
            {
                "checkpoint_id": row.checkpoint_id,
                "task_id": row.task_id,
                "write_idx": row.write_idx,
                "channel": row.channel,
                "value": row.value,
            }
            for row in rows
        ]


class ConcurrentGuardCheckpointSession(MemoryCheckpointSession):
    def __init__(self) -> None:
        super().__init__()
        self.active_operations = 0
        self.max_active_operations = 0

    async def execute(self, statement: Executable) -> "MemoryCheckpointResult":
        self.active_operations += 1
        self.max_active_operations = max(self.max_active_operations, self.active_operations)
        try:
            await asyncio.sleep(0)
            return await super().execute(statement)
        finally:
            self.active_operations -= 1


class MemoryCheckpointResult:
    def __init__(self, rows: Sequence[Mapping[str, Any]]) -> None:
        self._rows = rows

    def mappings(self) -> "MemoryCheckpointResult":
        return self

    def one_or_none(self) -> Mapping[str, Any] | None:
        return self._rows[0] if self._rows else None

    def all(self) -> Sequence[Mapping[str, Any]]:
        return self._rows


def _uuid_value(params: Mapping[str, Any]) -> UUID:
    for value in params.values():
        if isinstance(value, UUID):
            return value
    raise AssertionError("statement must contain a UUID session id")


def _uuid_named(params: Mapping[str, Any], prefix: str) -> UUID:
    value = next((value for key, value in params.items() if key.startswith(prefix)), None)
    assert isinstance(value, UUID)
    return value


def _optional_uuid_named(params: Mapping[str, Any], prefix: str) -> UUID | None:
    value = next((value for key, value in params.items() if key.startswith(prefix)), None)
    assert isinstance(value, UUID) or value is None
    return value


def _string_value(params: Mapping[str, Any], prefix: str) -> str:
    value = next((value for key, value in params.items() if key.startswith(prefix)), None)
    assert isinstance(value, str)
    return value


def _int_value(params: Mapping[str, Any], prefix: str) -> int:
    value = next((value for key, value in params.items() if key.startswith(prefix)), None)
    assert type(value) is int
    return value


def _optional_int_value(params: Mapping[str, Any], prefix: str) -> int | None:
    value = next((value for key, value in params.items() if key.startswith(prefix)), None)
    assert type(value) is int or value is None
    return value


def _insert_parameter_rows(params: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    grouped: dict[int, dict[str, Any]] = {}
    for key, value in params.items():
        prefix, separator, index = key.rpartition("_m")
        if separator != "" and index.isdigit():
            grouped.setdefault(int(index), {})[prefix] = value
    if grouped:
        return [grouped[index] for index in sorted(grouped)]
    return [params]


def _checkpoint_id_values(params: Mapping[str, Any]) -> set[str]:
    values: set[str] = set()
    for key, value in params.items():
        if not key.startswith("checkpoint_id"):
            continue
        if isinstance(value, str):
            values.add(value)
        elif isinstance(value, Sequence):
            items = cast(Sequence[object], value)
            values.update(item for item in items if isinstance(item, str))
    return values
