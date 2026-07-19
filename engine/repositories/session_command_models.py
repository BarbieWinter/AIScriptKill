"""Domain models and canonical encoding for durable MP-3 commands."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, cast
from uuid import UUID

from pydantic import BaseModel, TypeAdapter

from engine.api.schemas.actions import ActionResponse

ReceiptStatus = Literal["processing", "succeeded", "rejected", "failed"]


@dataclass(frozen=True, slots=True)
class CommandReceipt:
    session_id: UUID
    command_id: UUID
    request_sha256: str
    status: ReceiptStatus
    expected_revision: int | None
    base_revision: int | None
    result_revision: int | None
    result: ActionResponse | None
    error_code: str | None
    error_details: dict[str, object]
    event_sequence_from: int | None
    event_sequence_to: int | None
    request_payload: dict[str, object] = field(default_factory=dict)
    base_state: dict[str, object] | None = None
    base_state_sha256: str | None = None
    base_checkpoint_id: str | None = None
    checkpoint_id: str | None = None
    state_sha256: str | None = None
    attempt_count: int = 1
    lease_expires_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    completed_at: datetime | None = None


def canonical_command_payload(payload: object) -> dict[str, object]:
    """Return the stable request projection hashed by a command receipt."""

    if isinstance(payload, BaseModel):
        raw = cast(dict[str, object], payload.model_dump(mode="json", exclude={"command_id"}))
        return dict(raw)
    if isinstance(payload, Mapping):
        raw = cast(Mapping[object, object], payload)
        return {str(key): value for key, value in raw.items() if key != "command_id"}
    raise TypeError("command payload must be a mapping or Pydantic model")


def command_request_sha256(payload: object) -> str:
    """Hash canonical compact UTF-8 JSON with sorted keys."""

    encoded = json.dumps(
        canonical_command_payload(payload),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def action_response_from_json(value: object) -> ActionResponse | None:
    """Decode a stored action union without accepting arbitrary result objects."""

    if value is None:
        return None
    return cast(ActionResponse, TypeAdapter(ActionResponse).validate_python(value))
