from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

import asyncpg

from autoskill.core.events import EventEnvelope
from autoskill.db.pool import AsyncpgPoolOwner
from autoskill.db.workspaces import ensure_workspace


@dataclass(frozen=True)
class EventIngestSummary:
    accepted: int = 0
    duplicate: int = 0
    rejected: int = 0


class EventStore(Protocol):
    async def ingest_events(self, events: Sequence[EventEnvelope]) -> EventIngestSummary:
        """Persist already-redacted events idempotently."""


class NullEventStore:
    async def ingest_events(self, events: Sequence[EventEnvelope]) -> EventIngestSummary:
        return EventIngestSummary(accepted=len(events))


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


async def _insert_event(conn: asyncpg.Connection, workspace_id: UUID, event: EventEnvelope) -> bool:
    event_id = await conn.fetchval(
        """
        INSERT INTO autoskill.raw_events (
          event_id,
          workspace_id,
          trace_id,
          span_id,
          parent_span_id,
          session_id,
          turn_id,
          event_type,
          occurred_at,
          source,
          trust,
          taint,
          redaction_state,
          payload_hash,
          payload,
          plugin_version,
          openclaw_version
        )
        VALUES (
          $1, $2, $3, $4, $5, $6, $7, $8, $9, $10,
          $11, $12, $13, $14, $15::jsonb, $16, $17
        )
        ON CONFLICT (event_id) DO NOTHING
        RETURNING event_id
        """,
        event.event_id,
        workspace_id,
        event.trace_id,
        event.span_id,
        event.parent_span_id,
        event.session_id,
        event.turn_id,
        event.event_type,
        event.occurred_at,
        event.source,
        str(event.trust),
        event.taint,
        str(event.redaction_state),
        event.payload_hash,
        json.dumps(event.payload, sort_keys=True, separators=(",", ":")),
        event.plugin_version,
        event.openclaw_version,
    )
    return event_id is not None
