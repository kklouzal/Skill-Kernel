from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

import asyncpg

from autoskill.core.events import EventEnvelope
from autoskill.db.pool import AsyncpgPoolOwner
from autoskill.db.workspaces import ensure_workspace


@dataclass(frozen=True)
class EventRecord:
    event_id: UUID
    workspace_id: UUID | None
    workspace_key: str | None
    trace_id: UUID | None
    span_id: UUID | None
    parent_span_id: UUID | None
    agent_id: str | None
    session_id: str | None
    turn_id: str | None
    event_type: str
    occurred_at: datetime
    source: str
    source_event_key: str | None
    trust: str
    taint: list[str]
    redaction_state: str
    evidence_fidelity: str
    raw_evidence_record_id: UUID | None
    payload_hash: str
    payload: dict[str, Any]
    plugin_version: str | None
    openclaw_version: str | None
    inserted_at: datetime

    @classmethod
    def from_row(cls, row: asyncpg.Record | dict[str, Any]) -> EventRecord:
        return cls(
            event_id=row["event_id"],
            workspace_id=_row_get(row, "workspace_id"),
            workspace_key=_row_get(row, "workspace_key"),
            trace_id=_row_get(row, "trace_id"),
            span_id=_row_get(row, "span_id"),
            parent_span_id=_row_get(row, "parent_span_id"),
            agent_id=_row_get(row, "agent_id"),
            session_id=_row_get(row, "session_id"),
            turn_id=_row_get(row, "turn_id"),
            event_type=row["event_type"],
            occurred_at=row["occurred_at"],
            source=row["source"],
            source_event_key=_row_get(row, "source_event_key"),
            trust=row["trust"],
            taint=list(row["taint"]),
            redaction_state=row["redaction_state"],
            evidence_fidelity=_row_get(row, "evidence_fidelity") or "redacted_derivative",
            raw_evidence_record_id=_row_get(row, "raw_evidence_record_id"),
            payload_hash=row["payload_hash"],
            payload=_json_dict(row["payload"]),
            plugin_version=_row_get(row, "plugin_version"),
            openclaw_version=_row_get(row, "openclaw_version"),
            inserted_at=row["inserted_at"],
        )

    def to_json(self) -> dict[str, Any]:
        payload_keys = sorted(self.payload.keys())
        return {
            "object_type": "captured_event",
            "object_id": str(self.event_id),
            "event_id": str(self.event_id),
            "workspace_id": str(self.workspace_id) if self.workspace_id else None,
            "workspace_key": self.workspace_key,
            "trace_id": str(self.trace_id) if self.trace_id else None,
            "span_id": str(self.span_id) if self.span_id else None,
            "parent_span_id": str(self.parent_span_id) if self.parent_span_id else None,
            "agent_id": self.agent_id,
            "session_id": self.session_id,
            "turn_id": self.turn_id,
            "event_type": self.event_type,
            "occurred_at": self.occurred_at.isoformat(),
            "source": self.source,
            "source_event_key": self.source_event_key,
            "trust": self.trust,
            "taint": self.taint,
            "redaction_state": self.redaction_state,
            "evidence_fidelity": self.evidence_fidelity,
            "raw_evidence_record_id": (
                str(self.raw_evidence_record_id) if self.raw_evidence_record_id else None
            ),
            "payload_hash": self.payload_hash,
            "payload_keys": payload_keys,
            "plugin_version": self.plugin_version,
            "openclaw_version": self.openclaw_version,
            "inserted_at": self.inserted_at.isoformat(),
            "title": f"{self.event_type} {self.event_id}",
            "summary": (
                f"{self.source} event; redaction={self.redaction_state}; "
                f"payload_keys={len(payload_keys)}"
            ),
            "details_url": f"/admin/objects/captured_event/{self.event_id}",
            "content_policy": {
                "raw_available": False,
                "raw_reason": "raw-content-disabled",
                "redaction_state": self.redaction_state,
            },
        }


@dataclass(frozen=True)
class EventIngestSummary:
    accepted: int = 0
    duplicate: int = 0
    rejected: int = 0


class EventStore(Protocol):
    async def ingest_events(self, events: Sequence[EventEnvelope]) -> EventIngestSummary:
        """Persist already-redacted events idempotently."""

    async def list_events(
        self,
        *,
        workspace_key: str | None = None,
        event_type: str | None = None,
        trace_id: UUID | None = None,
        limit: int = 50,
    ) -> list[EventRecord]:
        """Return a bounded, content-safe event history read model."""

    async def get_event(
        self,
        *,
        event_id: UUID,
        workspace_key: str | None = None,
    ) -> EventRecord | None:
        """Fetch one content-safe event microscope record."""


class NullEventStore:
    def __init__(self) -> None:
        self.events: list[EventEnvelope] = []

    async def ingest_events(self, events: Sequence[EventEnvelope]) -> EventIngestSummary:
        self.events.extend(events)
        return EventIngestSummary(accepted=len(events))

    async def list_events(
        self,
        *,
        workspace_key: str | None = None,
        event_type: str | None = None,
        trace_id: UUID | None = None,
        limit: int = 50,
    ) -> list[EventRecord]:
        bounded_limit = max(1, min(limit, 500))
        records: list[EventRecord] = []
        for event in reversed(self.events):
            if workspace_key is not None and event.workspace_id != workspace_key:
                continue
            if event_type is not None and event.event_type != event_type:
                continue
            if trace_id is not None and event.trace_id != trace_id:
                continue
            records.append(_record_from_envelope(event))
            if len(records) >= bounded_limit:
                break
        return records

    async def get_event(
        self,
        *,
        event_id: UUID,
        workspace_key: str | None = None,
    ) -> EventRecord | None:
        for event in reversed(self.events):
            if event.event_id == event_id and (
                workspace_key is None or event.workspace_id == workspace_key
            ):
                return _record_from_envelope(event)
        return None


class AsyncpgEventStore(AsyncpgPoolOwner):
    def __init__(self, database_url: str, *, statement_timeout_ms: int = 30_000) -> None:
        super().__init__(database_url, statement_timeout_ms=statement_timeout_ms)

    async def ingest_events(self, events: Sequence[EventEnvelope]) -> EventIngestSummary:
        if not events:
            return EventIngestSummary()

        pool = await self._get_pool()
        accepted = 0
        duplicate = 0

        async with pool.acquire() as conn, conn.transaction():
            workspace_ids = {}
            for event in events:
                workspace_id = workspace_ids.get(event.workspace_id)
                if workspace_id is None:
                    workspace_id = await ensure_workspace(conn, event.workspace_id)
                    workspace_ids[event.workspace_id] = workspace_id

                inserted = await _insert_event(conn, workspace_id, event)
                if inserted:
                    accepted += 1
                else:
                    duplicate += 1

        return EventIngestSummary(accepted=accepted, duplicate=duplicate)

    async def list_events(
        self,
        *,
        workspace_key: str | None = None,
        event_type: str | None = None,
        trace_id: UUID | None = None,
        limit: int = 50,
    ) -> list[EventRecord]:
        bounded_limit = max(1, min(limit, 500))
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT
                  re.*,
                  w.external_key AS workspace_key
                FROM autoskill.raw_events re
                JOIN autoskill.workspaces w USING (workspace_id)
                WHERE ($1::text IS NULL OR w.external_key = $1)
                  AND ($2::text IS NULL OR re.event_type = $2)
                  AND ($3::uuid IS NULL OR re.trace_id = $3)
                ORDER BY re.occurred_at DESC, re.inserted_at DESC, re.event_id DESC
                LIMIT $4
                """,
                workspace_key,
                event_type,
                trace_id,
                bounded_limit,
            )
        return [EventRecord.from_row(row) for row in rows]

    async def get_event(
        self,
        *,
        event_id: UUID,
        workspace_key: str | None = None,
    ) -> EventRecord | None:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT
                  re.*,
                  w.external_key AS workspace_key
                FROM autoskill.raw_events re
                JOIN autoskill.workspaces w USING (workspace_id)
                WHERE re.event_id = $1
                  AND ($2::text IS NULL OR w.external_key = $2)
                """,
                event_id,
                workspace_key,
            )
        return EventRecord.from_row(row) if row else None


async def _insert_event(conn: asyncpg.Connection, workspace_id: UUID, event: EventEnvelope) -> bool:
    event_id = await conn.fetchval(
        """
        INSERT INTO autoskill.raw_events (
          event_id,
          workspace_id,
          trace_id,
          span_id,
          parent_span_id,
          agent_id,
          session_id,
          turn_id,
          event_type,
          occurred_at,
          source,
          source_event_key,
          trust,
          taint,
          redaction_state,
          evidence_fidelity,
          raw_evidence_record_id,
          payload_hash,
          payload,
          plugin_version,
          openclaw_version
        )
        VALUES (
          $1, $2, $3, $4, $5, $6, $7, $8, $9, $10,
          $11, $12, $13, $14, $15, $16, $17, $18, $19::jsonb, $20, $21
        )
        ON CONFLICT DO NOTHING
        RETURNING event_id
        """,
        event.event_id,
        workspace_id,
        event.trace_id,
        event.span_id,
        event.parent_span_id,
        event.agent_id,
        event.session_id,
        event.turn_id,
        event.event_type,
        event.occurred_at,
        event.source,
        event.source_event_key,
        str(event.trust),
        event.taint,
        str(event.redaction_state),
        event.evidence_fidelity,
        event.raw_evidence_record_id,
        event.payload_hash,
        json.dumps(event.payload, sort_keys=True, separators=(",", ":")),
        event.plugin_version,
        event.openclaw_version,
    )
    return event_id is not None


def _record_from_envelope(event: EventEnvelope) -> EventRecord:
    return EventRecord(
        event_id=event.event_id,
        workspace_id=None,
        workspace_key=event.workspace_id,
        trace_id=event.trace_id,
        span_id=event.span_id,
        parent_span_id=event.parent_span_id,
        agent_id=event.agent_id,
        session_id=event.session_id,
        turn_id=event.turn_id,
        event_type=event.event_type,
        occurred_at=event.occurred_at,
        source=event.source,
        source_event_key=event.source_event_key,
        trust=str(event.trust),
        taint=list(event.taint),
        redaction_state=str(event.redaction_state),
        evidence_fidelity=event.evidence_fidelity,
        raw_evidence_record_id=event.raw_evidence_record_id,
        payload_hash=event.payload_hash or "",
        payload=event.payload,
        plugin_version=event.plugin_version,
        openclaw_version=event.openclaw_version,
        inserted_at=event.occurred_at,
    )


def _row_get(row: asyncpg.Record | dict[str, Any], key: str) -> Any:
    if isinstance(row, dict):
        return row.get(key)
    try:
        return row[key]
    except KeyError:
        return None


def _json_dict(value: object) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str):
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else {}
    return {}
