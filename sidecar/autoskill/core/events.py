from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from autoskill.core.enums import RedactionState, TrustClass
from autoskill.core.hashing import sha256_json
from autoskill.core.redaction import redact_payload
from pydantic import BaseModel, Field, field_validator


class EventEnvelope(BaseModel):
    event_id: UUID = Field(default_factory=uuid4)
    schema_version: int = 1
    workspace_id: str
    trace_id: UUID | None = None
    span_id: UUID | None = None
    parent_span_id: UUID | None = None
    agent_id: str | None = None
    session_id: str | None = None
    turn_id: str | None = None
    event_type: str
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    source: str = "openclaw-plugin"
    trust: TrustClass
    taint: list[str] = Field(default_factory=list)
    redaction_state: RedactionState = RedactionState.REDACTED
    payload_hash: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    plugin_version: str | None = None
    openclaw_version: str | None = None

    @field_validator("event_type")
    @classmethod
    def event_type_must_be_nonempty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("event_type must be non-empty")
        return value

    def redacted(self) -> EventEnvelope:
        payload = redact_payload(self.payload)
        return self.model_copy(
            update={
                "payload": payload,
                "payload_hash": sha256_json(payload),
                "redaction_state": RedactionState.REDACTED,
            }
        )


class IngestRequest(BaseModel):
    events: list[EventEnvelope]


class IngestResult(BaseModel):
    accepted: int
    duplicate: int = 0
    rejected: int = 0
