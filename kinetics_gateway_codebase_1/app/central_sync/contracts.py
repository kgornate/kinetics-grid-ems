from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator, model_validator

Priority = Literal["P0", "P1", "P2", "P3", "P4"]
PRIORITY_RANK: dict[str, int] = {"P0": 0, "P1": 1, "P2": 2, "P3": 3, "P4": 4}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class LogicalMessage(BaseModel):
    """Frozen Northbound v1.3-compatible logical message envelope.

    The fields through ``gateway_software_version`` come from the frozen
    Northbound workbook. ``priority`` is retained as an additive transport
    hint because the production Northbound outbox/uploader already uses it.
    """

    schema_version: str
    message_id: str = Field(default_factory=lambda: str(uuid4()))
    gateway_id: str
    site_id: str
    organization_id: str
    stream: str
    substream: str | None = None
    sequence: int
    created_at_utc: str = Field(default_factory=utc_now_iso)
    record_count: int | None = None
    records: list[dict[str, Any]]
    compression: Literal["gzip", "none"] = "gzip"
    gateway_software_version: str
    priority: Priority = "P3"

    @field_validator("stream", "gateway_id", "site_id", "organization_id", "gateway_software_version")
    @classmethod
    def _nonempty(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("identity/stream fields must not be empty")
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

    @model_validator(mode="after")
    def _derive_record_count(self) -> "LogicalMessage":
        actual = len(self.records)
        if self.record_count is None:
            self.record_count = actual
        elif int(self.record_count) != actual:
            raise ValueError(f"record_count={self.record_count} does not match len(records)={actual}")
        return self

    @property
    def priority_rank(self) -> int:
        return PRIORITY_RANK[self.priority]


class TransportBatch(BaseModel):
    """Same transport wrapper used by the Northbound Central Sync uploader."""

    request_id: str = Field(default_factory=lambda: str(uuid4()))
    gateway_id: str
    sent_at_utc: str = Field(default_factory=utc_now_iso)
    messages: list[dict[str, Any]]


def make_message(
    *,
    schema_version: str,
    gateway_id: str,
    site_id: str,
    organization_id: str,
    gateway_software_version: str,
    stream: str,
    substream: str | None,
    sequence: int,
    priority: Priority,
    records: list[dict[str, Any]],
    compression: Literal["gzip", "none"] = "gzip",
    created_at_utc: str | None = None,
    message_id: str | None = None,
) -> LogicalMessage:
    kwargs: dict[str, Any] = {
        "schema_version": schema_version,
        "gateway_id": gateway_id,
        "site_id": site_id,
        "organization_id": organization_id,
        "gateway_software_version": gateway_software_version,
        "stream": stream,
        "substream": substream,
        "sequence": sequence,
        "priority": priority,
        "records": records,
        "record_count": len(records),
        "compression": compression,
    }
    if created_at_utc is not None:
        kwargs["created_at_utc"] = created_at_utc
    if message_id is not None:
        kwargs["message_id"] = message_id
    return LogicalMessage(**kwargs)
