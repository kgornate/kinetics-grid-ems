from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator

Priority = Literal["P0", "P1", "P2", "P3", "P4"]
PRIORITY_RANK: dict[str, int] = {"P0": 0, "P1": 1, "P2": 2, "P3": 3, "P4": 4}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class LogicalMessage(BaseModel):
    schema_version: str
    message_id: str = Field(default_factory=lambda: str(uuid4()))
    gateway_id: str
    site_id: str
    stream: str
    substream: str | None = None
    sequence: int
    created_at_utc: str = Field(default_factory=utc_now_iso)
    priority: Priority = "P3"
    records: list[dict[str, Any]]

    @field_validator("stream")
    @classmethod
    def _stream_nonempty(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("stream must not be empty")
        return value

    @field_validator("sequence")
    @classmethod
    def _sequence_nonnegative(cls, value: int) -> int:
        if value < 0:
            raise ValueError("sequence must be >= 0")
        return value

    @field_validator("records")
    @classmethod
    def _records_nonempty(cls, value: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not value:
            raise ValueError("records must not be empty")
        return value

    @property
    def priority_rank(self) -> int:
        return PRIORITY_RANK[self.priority]


class TransportBatch(BaseModel):
    request_id: str = Field(default_factory=lambda: str(uuid4()))
    gateway_id: str
    sent_at_utc: str = Field(default_factory=utc_now_iso)
    messages: list[dict[str, Any]]


def make_message(
    *,
    schema_version: str,
    gateway_id: str,
    site_id: str,
    stream: str,
    substream: str | None,
    sequence: int,
    priority: Priority,
    records: list[dict[str, Any]],
    created_at_utc: str | None = None,
    message_id: str | None = None,
) -> LogicalMessage:
    kwargs: dict[str, Any] = {
        "schema_version": schema_version,
        "gateway_id": gateway_id,
        "site_id": site_id,
        "stream": stream,
        "substream": substream,
        "sequence": sequence,
        "priority": priority,
        "records": records,
    }
    if created_at_utc is not None:
        kwargs["created_at_utc"] = created_at_utc
    if message_id is not None:
        kwargs["message_id"] = message_id
    return LogicalMessage(**kwargs)
